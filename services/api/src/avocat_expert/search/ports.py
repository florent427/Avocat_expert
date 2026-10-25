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
    enabled: bool
    detail: str

    def search(
        self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None
    ) -> list[LexicalHit]: ...


class DisabledSemanticSearcher:
    """Canal sémantique désactivé tant qu'aucun modèle d'embeddings n'est
    choisi, évalué et autorisé (voir ADR 0006)."""

    name = "semantique"
    enabled = False
    detail = "désactivé : aucun fournisseur d'embeddings configuré et validé"

    def search(self, query: str, as_of: date, limit: int, documents: frozenset[str] | None = None) -> list[LexicalHit]:
        return []
