"""Ports de recherche : le code métier ne dépend d'aucun moteur particulier."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from avocat_expert.storage.corpus import LexicalHit


class LexicalSearcher(Protocol):
    name: str
    ranking: str

    def search(self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None) -> list[LexicalHit]:
        """``documents`` : identifiants des seuls textes à interroger (texte nommé
        dans la question) ; la restriction est appliquée par le moteur, avant
        classement."""
        ...


class SemanticSearcher(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    @property
    def detail(self) -> str: ...

    def search(
        self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None
    ) -> list[LexicalHit]: ...


class DisabledSemanticSearcher:
    """Canal sémantique désactivé : aucun modèle d'embeddings configuré
    (ADR 0006, 0017), ou configuration incomplète (motif dans ``detail``)."""

    name = "semantique"
    enabled = False

    def __init__(self, detail: str = "désactivé : aucun modèle d'embeddings configuré") -> None:
        self.detail = detail

    def search(self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None) -> list[LexicalHit]:
        return []
