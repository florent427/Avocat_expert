"""Canal lexical OpenSearch (ADR 0005, phase D).

L'index ne sert qu'au classement : les versions trouvées sont relues dans
PostgreSQL, source de vérité des citations et de leur vérification.

API REST utilisées (documentation OpenSearch 3.x vérifiée le 2026-10-25) :
``PUT /{index}`` (paramètres, correspondances), ``POST /_bulk`` (NDJSON,
``application/x-ndjson``, corps terminé par un saut de ligne),
``POST /{index}/_search``, ``POST /_aliases`` (bascule atomique),
``POST /{index}/_refresh``, ``DELETE /{index}``, ``GET /_alias/{alias}``.

Client minimal (bibliothèque standard) : aucune dépendance supplémentaire.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from datetime import date
from typing import Any, Protocol
from urllib.parse import quote, urlsplit

from avocat_expert.embedding.models import ModelSpec
from avocat_expert.storage.corpus import CorpusRepository, LexicalHit

#: Analyseur français documenté (élision, minuscules, mots vides, racinisation
#: légère), suivi d'un repli des accents, cohérent avec la configuration
#: PostgreSQL ``avx_fr`` (french_stem + unaccent).
ANALYSIS: dict[str, Any] = {
    "filter": {
        "avx_elision": {
            "type": "elision",
            "articles_case": True,
            "articles": ["l", "m", "t", "qu", "n", "s", "j", "d", "c", "jusqu", "quoiqu", "lorsqu", "puisqu"],
        },
        "avx_stop": {"type": "stop", "stopwords": "_french_"},
        "avx_stem": {"type": "stemmer", "language": "light_french"},
    },
    "analyzer": {
        "avx_fr": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["avx_elision", "lowercase", "avx_stop", "avx_stem", "asciifolding"],
        }
    },
}

MAPPINGS: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "official_id": {"type": "keyword"},
        "version_row_id": {"type": "keyword"},
        "document_official_id": {"type": "keyword"},
        "document_title": {"type": "text", "analyzer": "avx_fr"},
        "provision_number": {"type": "keyword"},
        "section_path": {"type": "text", "analyzer": "avx_fr"},
        "text": {"type": "text", "analyzer": "avx_fr"},
        "source_status": {"type": "keyword"},
        "valid_from": {"type": "date", "format": "strict_date"},
        "valid_to": {"type": "date", "format": "strict_date"},
        "end_undetermined": {"type": "boolean"},
        "dates_unknown": {"type": "boolean"},
    },
}

INDEX_VERSION = "v2"

#: Graphe HNSW (moteur faiss, valeurs par défaut documentées : m = 16,
#: ef_construction = 100). Filtrage « efficace » (pendant le parcours du graphe,
#: recherche exacte si le filtre est très sélectif) : faiss et lucene
#: uniquement (documentation k-NN OpenSearch 3.x).
HNSW_PARAMETERS = {"m": 16, "ef_construction": 100}


def index_body(replicas: int = 0, embedding: ModelSpec | None = None) -> dict[str, Any]:
    """Paramètres et correspondances ; avec un modèle, champ vectoriel de sa
    dimension et clé du modèle dans ``_meta`` (une requête n'est jamais
    vectorisée par un autre modèle que celui de l'index)."""
    index: dict[str, Any] = {"number_of_shards": 1, "number_of_replicas": replicas, "codec": "best_compression"}
    mappings: dict[str, Any] = {**MAPPINGS, "properties": dict(MAPPINGS["properties"])}
    mappings["_meta"] = {"embedding_model": embedding.key if embedding else None}
    if embedding is not None:
        index["knn"] = True
        mappings["properties"]["embedding"] = {
            "type": "knn_vector",
            "dimension": embedding.dimension,
            "method": {"name": "hnsw", "engine": "faiss", "space_type": "cosinesimil", "parameters": HNSW_PARAMETERS},
        }
    return {"settings": {"index": index, "analysis": ANALYSIS}, "mappings": mappings}


def index_embedding_model(client: OpenSearchClient, alias: str) -> str | None:
    """Clé du modèle des vecteurs de l'index désigné par l'alias (``_meta``)."""
    mappings = client.request("GET", f"/{quote(alias)}/_mapping", ok_missing=True) or {}
    keys = {(m.get("mappings", {}).get("_meta") or {}).get("embedding_model") for m in mappings.values()}
    return keys.pop() if len(keys) == 1 else None


class OpenSearchError(RuntimeError):
    pass


class OpenSearchClient:
    def __init__(self, base_url: str, *, username: str = "", password: str = "", timeout_s: float = 30.0) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise OpenSearchError(f"URL OpenSearch invalide : {base_url!r}")
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._auth = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode() if username else None

    def request(
        self, method: str, path: str, body: Any = None, *, ndjson: str | None = None, ok_missing: bool = False
    ) -> Any:
        data: bytes | None = None
        headers = {"Accept": "application/json"}
        if ndjson is not None:
            data, headers["Content-Type"] = ndjson.encode("utf-8"), "application/x-ndjson"
        elif body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
        if self._auth:
            headers["Authorization"] = self._auth
        req = urllib.request.Request(self._base + path, data=data, headers=headers, method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:  # noqa: S310 — URL configurée
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if ok_missing and exc.code == 404:
                return None
            detail = exc.read()[:500].decode("utf-8", errors="replace")
            raise OpenSearchError(f"{method} {path} : HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise OpenSearchError(f"{method} {path} : {exc.reason}") from exc
        return json.loads(raw) if raw else None

    def bulk(
        self, actions: list[tuple[dict[str, Any], dict[str, Any] | None]], *, tolerate_missing_deletes: bool = False
    ) -> int:
        """Exécute un lot d'actions ; lève une erreur si une action échoue
        (sauf, si demandé, la suppression d'un document déjà absent)."""
        if not actions:
            return 0
        lines = []
        for action, source in actions:
            lines.append(json.dumps(action, ensure_ascii=False))
            if source is not None:
                lines.append(json.dumps(source, ensure_ascii=False))
        result = self.request("POST", "/_bulk", ndjson="\n".join(lines) + "\n")
        failures = [
            op
            for item in result.get("items", [])
            for kind, op in item.items()
            if op.get("status", 200) >= 300
            and not (tolerate_missing_deletes and kind == "delete" and op.get("status") == 404)
        ]
        if failures:
            raise OpenSearchError(f"échec d'indexation pour {len(failures)} élément(s) : {failures[:3]}")
        return len(actions)


def temporal_filter(as_of: date) -> list[dict[str, Any]]:
    """Versions en vigueur à la date (période semi-ouverte [début, fin)).

    Une version à début non fixé ou à dates inconnues n'a pas de ``valid_from`` :
    elle n'est jamais retenue. Une version à fin non fixée est retenue ; son
    applicabilité au-delà de la date de connaissance est qualifiée par le
    moteur de vérification (INDETERMINE)."""
    day = as_of.isoformat()
    return [
        {"range": {"valid_from": {"lte": day}}},
        {
            "bool": {
                "should": [
                    {"range": {"valid_to": {"gt": day}}},
                    {"bool": {"must_not": {"exists": {"field": "valid_to"}}}},
                ],
                "minimum_should_match": 1,
            }
        },
    ]


#: Proximité des termes dans les intitulés de section (expression à 3 positions
#: près) et poids de ce signal. Mesuré sur le corpus complet (2026-10-25) :
#: « conditions d'attribution de l'allocation d'assurance » place l'article
#: L5422-1 au rang 6 au lieu d'au-delà du rang 200, les premiers résultats
#: appartenant tous à la sous-section « Conditions d'attribution ».
#: Calibrage provisoire sur 4 questions : à reprendre sur le corpus annoté (QUAL-01).
SECTION_PHRASE_SLOP = 3
SECTION_PHRASE_BOOST = 2.0


class OpenSearchLexicalSearcher:
    name = "lexical"
    ranking = (
        "BM25 OpenSearch (analyseur avx_fr : élision, mots vides, racinisation légère, repli d'accents) "
        f"sur le texte, renforcé par la proximité des termes dans les intitulés de section "
        f"(expression à {SECTION_PHRASE_SLOP} positions près, poids {SECTION_PHRASE_BOOST})"
    )

    def __init__(self, client: OpenSearchClient, alias: str, repository: CorpusRepository) -> None:
        self._client = client
        self._alias = alias
        self._repository = repository

    def search(self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None) -> list[LexicalHit]:
        filters = temporal_filter(as_of)
        if documents:
            filters.append({"terms": {"document_official_id": sorted(documents)}})
        body = {
            "size": limit,
            "_source": False,
            "track_total_hits": False,
            "query": {
                "bool": {
                    "should": [
                        {"match": {"text": {"query": query}}},
                        {
                            "match_phrase": {
                                "section_path": {
                                    "query": query,
                                    "slop": SECTION_PHRASE_SLOP,
                                    "boost": SECTION_PHRASE_BOOST,
                                }
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                    "filter": filters,
                }
            },
        }
        result = self._client.request("POST", f"/{quote(self._alias)}/_search", body)
        scored = [(hit["_id"], float(hit["_score"])) for hit in result["hits"]["hits"]]
        versions = self._repository.current_versions(sorted({official_id for official_id, _ in scored}))
        # Un document de l'index sans version courante (index en retard sur le
        # corpus) est ignoré : seule la base fait foi.
        return [LexicalHit(versions[official_id], score) for official_id, score in scored if official_id in versions]


class QueryEmbedder(Protocol):
    spec: ModelSpec

    def embed_queries(self, texts: list[str]) -> Any: ...


class OpenSearchSemanticSearcher:
    """Plus proches voisins (cosinus) parmi les versions en vigueur à la date,
    restreints le cas échéant aux textes nommés ; versions relues dans
    PostgreSQL. Score renvoyé : similarité cosinus (score OpenSearch
    ``cosinesimil`` = (1 + cos) / 2)."""

    name = "semantique"

    def __init__(
        self, client: OpenSearchClient, alias: str, repository: CorpusRepository, embedder: QueryEmbedder
    ) -> None:
        self._client = client
        self._alias = alias
        self._repository = repository
        self._embedder = embedder
        self._index_model: str | bool | None = False  # False : non encore lu

    def _ready(self) -> bool:
        if self._index_model is False:
            self._index_model = index_embedding_model(self._client, self._alias)
        return self._index_model == self._embedder.spec.key

    @property
    def enabled(self) -> bool:
        return self._ready()

    @property
    def detail(self) -> str:
        spec = self._embedder.spec
        if not self._ready():
            return (
                f"désactivé : l'index {self._alias} n'a pas été construit avec le modèle {spec.key} "
                "(reconstruction requise : avx indexer-recherche --complet)"
            )
        return (
            f"{spec.repository} (révision {spec.revision[:8]}, auto-hébergé, ONNX Runtime) ; "
            "plus proches voisins (HNSW faiss, cosinus) filtrés par date et par texte"
        )

    def search(self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None) -> list[LexicalHit]:
        if not self._ready():
            return []
        vector = [float(x) for x in self._embedder.embed_queries([query])[0]]
        filters = temporal_filter(as_of)
        if documents:
            filters.append({"terms": {"document_official_id": sorted(documents)}})
        body = {
            "size": limit,
            "_source": False,
            "query": {"knn": {"embedding": {"vector": vector, "k": limit, "filter": {"bool": {"filter": filters}}}}},
        }
        result = self._client.request("POST", f"/{quote(self._alias)}/_search", body)
        scored = [(hit["_id"], 2.0 * float(hit["_score"]) - 1.0) for hit in result["hits"]["hits"]]
        versions = self._repository.current_versions(sorted({official_id for official_id, _ in scored}))
        return [LexicalHit(versions[official_id], score) for official_id, score in scored if official_id in versions]
