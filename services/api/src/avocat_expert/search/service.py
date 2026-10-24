"""Service de recherche hybride.

Canaux : identifiant officiel, numéro d'article, lexical, sémantique (port).
Fusion : priorité aux correspondances exactes (identifiant, numéro), puis
fusion par rangs réciproques (RRF, k=60) des canaux lexical et sémantique.
Chaque résultat porte une référence traçable et un extrait littéral.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from avocat_expert.contracts.services import ChannelStatus, SearchHit, SearchResponse
from avocat_expert.search.ports import LexicalSearcher, SemanticSearcher
from avocat_expert.search.query import ParsedQuery, fold, parse_query, terms_of
from avocat_expert.storage.corpus import CorpusRepository, LexicalHit, VersionRecord

RRF_K = 60
EXACT_MATCH_BONUS = 1.0
MIN_EXCERPT_CHARS = 40
MAX_WINDOW_LINES = 3


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


def select_excerpt(text: str, query_terms: tuple[str, ...]) -> str:
    """Fenêtre d'au plus trois paragraphes consécutifs recouvrant le mieux les
    termes de la requête. Le texte est restitué littéralement (jamais réécrit)."""
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ""
    prefixes = {t[:5] for t in query_terms}

    def line_score(line: str) -> int:
        return sum(1 for t in set(terms_of(line)) if t[:5] in prefixes)

    scores = [line_score(line) for line in lines]
    best: tuple[int, int, int] = (-1, 0, 1)
    for start in range(len(lines)):
        for size in range(1, MAX_WINDOW_LINES + 1):
            end = start + size
            if end > len(lines):
                break
            if size > 1 and len("\n".join(lines[start : end - 1])) >= MIN_EXCERPT_CHARS:
                break  # inutile d'élargir une fenêtre déjà suffisante
            window_score = sum(scores[start:end])
            if window_score > best[0]:
                best = (window_score, start, end)
    _, start, end = best
    return "\n".join(lines[start:end])


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
        for candidate in exact:
            merge(candidate)
        for channel in (self._lexical, self._semantic):
            if not parsed.free_text:
                break
            for rank, hit in enumerate(channel.search(parsed.free_text, as_of, limit * 3), start=1):
                merge(_Candidate(hit.version, 1.0 / (RRF_K + rank), [channel.name]))

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
            ranking=f"correspondances exactes prioritaires puis RRF(k={RRF_K}) ; lexical : {self._lexical.ranking}",
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
