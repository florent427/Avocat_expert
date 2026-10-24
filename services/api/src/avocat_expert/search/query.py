"""Analyse déterministe de la requête : identifiants officiels et références d'articles."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_OFFICIAL_ID = re.compile(r"\b(LEGIARTI\d{12}|LEGITEXT\d{12}|JORFTEXT\d{12}|JORFARTI\d{12})\b")
# « article L. 5422-1 », « art. R321-14 », « L.125-2 », « D 251-1 ».
_PREFIXED_ARTICLE = re.compile(r"(?<![\w.])([LRDA])\s?\.?\s?(\d{1,5}(?:-\d{1,5})+|\d{2,5})(?![\w-])")
# « article 1240 » : numéro nu uniquement s'il est précédé du mot article.
_BARE_ARTICLE = re.compile(r"\bart(?:icle|\.)?\s+(\d{1,5}(?:-\d{1,5})*)(?![\w-])", re.IGNORECASE)

_STOPWORDS = frozenset(
    "les des une un le la de du et en au aux pour par sur dans est sont qui que quoi quel quelle quels "
    "quelles dont avec sans pas plus ou ne se sa son ses leur leurs ce cette ces il elle ils elles on "
    "nous vous je tu peut peuvent doit doivent etre avoir faire article articles code".split()
)


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    official_ids: tuple[str, ...]
    article_numbers: tuple[str, ...]
    #: Texte libre, références explicites retirées (entrée du canal lexical).
    free_text: str
    terms: tuple[str, ...]

    @property
    def has_explicit_references(self) -> bool:
        return bool(self.official_ids or self.article_numbers)


def fold(text: str) -> str:
    """Minuscules sans diacritiques (usage : comparaison, jamais affichage)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def terms_of(text: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z0-9]+", fold(text))
    return tuple(t for t in tokens if len(t) >= 3 and t not in _STOPWORDS)


def parse_query(raw: str) -> ParsedQuery:
    ids = tuple(dict.fromkeys(_OFFICIAL_ID.findall(raw)))
    numbers = [f"{m.group(1)}{m.group(2)}" for m in _PREFIXED_ARTICLE.finditer(raw)]
    numbers += [m.group(1) for m in _BARE_ARTICLE.finditer(raw)]
    free_text = _BARE_ARTICLE.sub(" ", _PREFIXED_ARTICLE.sub(" ", _OFFICIAL_ID.sub(" ", raw)))
    terms = terms_of(free_text)
    return ParsedQuery(
        raw=raw,
        official_ids=ids,
        article_numbers=tuple(dict.fromkeys(numbers)),
        free_text=" ".join(terms),
        terms=terms,
    )
