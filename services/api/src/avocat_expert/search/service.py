"""Service de recherche hybride.

Canaux : identifiant officiel, numéro d'article, lexical, sémantique (port).
Fusion : priorité aux correspondances exactes (identifiant, numéro), puis
fusion par rangs réciproques (RRF, k=60) des canaux lexical et sémantique.
Chaque résultat porte une référence traçable et un extrait littéral.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from avocat_expert.connectors.legi import SOURCE_CODE as LEGI_SOURCE_CODE
from avocat_expert.contracts.services import ChannelStatus, SearchHit, SearchResponse
from avocat_expert.search.excerpt import select_excerpt
from avocat_expert.search.ports import LexicalSearcher, SemanticSearcher
from avocat_expert.search.query import ParsedQuery, fold, parse_query, terms_of
from avocat_expert.storage.corpus import CorpusRepository, LexicalHit, VersionRecord

RRF_K = 60
EXACT_MATCH_BONUS = 1.0
#: Un résultat lexical dont le score est inférieur à cette fraction du meilleur
#: score lexical de la requête est écarté (bruit). Heuristique calibrée sur le
#: corpus technique seed_v0 : à recalibrer sur le corpus annoté par des juristes.
LEXICAL_RELATIVE_CUTOFF = 0.5


@dataclass(frozen=True)
class SearchOutcome:
    response: SearchResponse
    #: Constats de couverture (références introuvables, versions manquantes).
    notes: list[str]
    #: Références explicites (identifiants, numéros d'articles) demandées / résolues.
    explicit_requested: int
    explicit_resolved: int


@dataclass
class _Candidate:
    version: VersionRecord
    score: float = 0.0
    matched_by: list[str] = field(default_factory=list)


class HybridSearchService:
    def __init__(
        self,
        repository: CorpusRepository,
        lexical: LexicalSearcher,
        semantic: SemanticSearcher,
    ) -> None:
        self._repository = repository
        self._lexical = lexical
        self._semantic = semantic
        self._titles: list[tuple[str, str, str | None]] | None = None

    def _named_documents(self, raw: str) -> list[tuple[str, str]]:
        """Textes du corpus dont le titre (ou titre court) figure dans la question."""
        if self._titles is None:
            self._titles = self._repository.document_titles()
        folded = fold(raw)
        named = []
        for official_id, title, short_title in self._titles:
            for candidate in (title, short_title):
                if candidate and fold(candidate) in folded:
                    named.append((official_id, candidate))
                    break
        return named

    def _exact_candidates(self, parsed: ParsedQuery, as_of: date) -> tuple[list[_Candidate], list[str], int]:
        notes: list[str] = []
        exact: list[_Candidate] = []
        resolved = 0
        for official_id in parsed.official_ids:
            version = self._repository.get_current_version(official_id)
            if version is None:
                notes.append(f"identifiant {official_id} absent du corpus ingéré")
            else:
                resolved += 1
                exact.append(_Candidate(version, EXACT_MATCH_BONUS * 2, ["identifiant"]))
        folded_query = fold(parsed.raw)
        for number in parsed.article_numbers:
            versions = self._repository.find_in_force_by_number(number, as_of)
            named = [v for v in versions if fold(v.document_title) in folded_query]
            resolved += int(bool(versions))
            for version in named or versions:
                exact.append(_Candidate(version, EXACT_MATCH_BONUS, ["numero_article"]))
            for missing_id, title in self._repository.declared_but_missing(number, as_of):
                notes.append(
                    f"{title}, article {number} : la version {missing_id}, déclarée par la source pour "
                    f"cette date, n'est pas présente dans le corpus ingéré"
                )
            if not versions:
                notes.append(f"aucune version de l'article {number} en vigueur au {as_of} dans le corpus")
        return exact, notes, resolved

    def search(self, query: str, as_of: date, limit: int) -> SearchOutcome:
        parsed = parse_query(query)
        candidates: dict[str, _Candidate] = {}

        def merge(candidate: _Candidate) -> None:
            key = candidate.version.official_id
            existing = candidates.get(key)
            if existing is None:
                candidates[key] = candidate
                return
            existing.score += candidate.score
            existing.matched_by.extend(m for m in candidate.matched_by if m not in existing.matched_by)

        exact, notes, resolved = self._exact_candidates(parsed, as_of)
        knowledge = self._repository.knowledge_date(LEGI_SOURCE_CODE)
        if knowledge is None:
            notes.append("date de la dernière livraison intégrée inconnue : état du corpus non daté")
        elif as_of > knowledge:
            notes.append(
                f"date demandée ({as_of}) postérieure à la dernière livraison intégrée ({knowledge}) : "
                "les modifications publiées depuis ne sont pas connues du corpus"
            )
        for candidate in exact:
            merge(candidate)

        # Un texte nommé dans la question (« code du travail ») restreint le
        # périmètre ; les mots de son titre ne sont pas des mots de contenu.
        named = self._named_documents(parsed.raw)
        title_terms = {t for _, title in named for t in terms_of(title)}
        content_terms = [t for t in parsed.terms if t not in title_terms]
        explicit_found = resolved > 0
        if content_terms:
            for channel in (self._lexical, self._semantic):
                channel_hits = channel.search(" ".join(content_terms), as_of, limit * 3)
                if named:
                    allowed = {doc_id for doc_id, _ in named}
                    channel_hits = [h for h in channel_hits if h.version.document_official_id in allowed]
                if channel is self._lexical and channel_hits:
                    floor = channel_hits[0].score * LEXICAL_RELATIVE_CUTOFF
                    channel_hits = [h for h in channel_hits if h.score >= floor]
                for rank, hit in enumerate(channel_hits, start=1):
                    merge(_Candidate(hit.version, 1.0 / (RRF_K + rank), [channel.name]))
        elif not explicit_found and parsed.terms:
            notes.append("la question ne contient pas de terme de contenu exploitable en dehors du nom du texte")

        ranked = sorted(candidates.values(), key=lambda c: (-c.score, c.version.official_id))[:limit]
        hits = [
            SearchHit(
                reference=c.version.reference,
                excerpt=select_excerpt(c.version.text_content, parsed.terms),
                score=round(c.score, 6),
                matched_by=c.matched_by,
            )
            for c in ranked
        ]
        channels = [
            ChannelStatus(channel="identifiant", enabled=True, detail="identifiants LEGI/JORF"),
            ChannelStatus(channel="numero_article", enabled=True, detail="numéros d'articles (L, R, D, A)"),
            ChannelStatus(channel=self._lexical.name, enabled=True, detail=self._lexical.ranking),
            ChannelStatus(channel=self._semantic.name, enabled=self._semantic.enabled, detail=self._semantic.detail),
        ]
        response = SearchResponse(
            as_of=as_of,
            hits=hits,
            channels=channels,
            ranking=(
                f"correspondances exactes prioritaires puis RRF(k={RRF_K}) ; lexical : {self._lexical.ranking}, "
                f"seuil relatif {LEXICAL_RELATIVE_CUTOFF}, restreint au texte nommé dans la question le cas échéant"
            ),
        )
        return SearchOutcome(
            response=response,
            notes=notes,
            explicit_requested=len(parsed.official_ids) + len(parsed.article_numbers),
            explicit_resolved=resolved,
        )


class PostgresLexicalSearcher:
    name = "lexical"
    ranking = "BM25 (k1=1,2 ; b=0,75) sur tsvector PostgreSQL, configuration avx_fr"

    def __init__(self, repository: CorpusRepository) -> None:
        self._repository = repository

    def search(self, query: str, as_of: date, limit: int) -> list[LexicalHit]:
        return self._repository.lexical_search(query, as_of, limit)
