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
from typing import Any
from urllib.parse import quote, urlsplit

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

INDEX_VERSION = "v1"


def index_body(replicas: int = 0) -> dict[str, Any]:
    return {
        "settings": {
            "index": {"number_of_shards": 1, "number_of_replicas": replicas, "codec": "best_compression"},
            "analysis": ANALYSIS,
        },
        "mappings": MAPPINGS,
    }


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
