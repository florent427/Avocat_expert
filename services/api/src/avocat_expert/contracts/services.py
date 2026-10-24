"""Contrats des services exposés (recherche, réponse sourcée, vérification)."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from avocat_expert.contracts.common import (
    CheckOutcome,
    ClaimKind,
    SourceReference,
    Strict,
    SupportStatus,
    Verdict,
)


class SearchRequest(Strict):
    query: str = Field(min_length=2, max_length=2000)
    as_of: date | None = Field(default=None, description="Date d'appréciation ; défaut : date du jour")
    limit: int = Field(default=10, ge=1, le=50)


class SearchHit(Strict):
    reference: SourceReference
    excerpt: str = Field(description="Extrait littéral du texte de la version")
    score: float
    matched_by: list[str] = Field(description="Canaux ayant produit le résultat : identifiant, lexical, sémantique")


class ChannelStatus(Strict):
    channel: str
    enabled: bool
    detail: str


class SearchResponse(Strict):
    as_of: date
    hits: list[SearchHit]
    channels: list[ChannelStatus]
    ranking: str = Field(description="Méthode de classement effectivement utilisée")


class CitationVerificationRequest(Strict):
    official_id: str = Field(max_length=64)
    quote: str = Field(min_length=1, max_length=20000)
    as_of: date
    territory: str | None = Field(default=None, max_length=32)


class CitationCheck(Strict):
    check: str
    outcome: CheckOutcome
    detail: str


class CitationVerification(Strict):
    official_id: str
    verdict: Verdict
    checks: list[CitationCheck]
    uncertainties: list[str]
    quote_start: int | None = None
    quote_end: int | None = None
    version_in_force_at_date: str | None = None
    engine_version: str
    contract_version: str


class AnswerRequest(Strict):
    question: str = Field(min_length=3, max_length=4000)
    as_of: date | None = None
    territory: str | None = Field(default=None, max_length=32)
    max_sources: int = Field(default=3, ge=1, le=10)


class SourcedStatement(Strict):
    kind: ClaimKind
    text: str
    citation: SourceReference | None
    quote: str | None
    verification: CitationVerification | None
    support: SupportStatus


class SourcedAnswer(Strict):
    question_sha256: str
    as_of: date
    mode: str = Field(description="Ex. EXTRACTIF : aucune génération de texte par un modèle")
    status: SupportStatus
    summary: str
    statements: list[SourcedStatement]
    uncertainties: list[str]
    disclaimer: str
    search: SearchResponse
