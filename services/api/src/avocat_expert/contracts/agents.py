"""Contrats des agents.

Les agents ne communiquent qu'au moyen de ces enveloppes. Un agent reçoit une
``AgentTask`` et renvoie un ``AgentResult`` ; le contenu métier (``payload``)
est lui-même un modèle typé propre à chaque agent. Le routage est décidé par
l'orchestrateur à partir d'une ``ComplexityAssessment`` : les agents ne sont
pas exécutés systématiquement.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from avocat_expert.contracts.common import ClaimKind, SourceReference, Strict, SupportStatus
from avocat_expert.contracts.services import CitationVerification


class AgentName(StrEnum):
    ORCHESTRATEUR = "orchestrateur"
    QUALIFICATION = "qualification"
    RECHERCHE_LEGISLATIVE = "recherche_legislative"
    JURISPRUDENCE = "jurisprudence"
    ANALYSE_FACTUELLE = "analyse_factuelle"
    CHRONOLOGIE_PREUVES = "chronologie_preuves"
    PROCEDURE = "procedure"
    ARGUMENTATION_FAVORABLE = "argumentation_favorable"
    CONTRADICTION = "contradiction"
    SYNTHESE = "synthese"
    VERIFICATEUR = "verificateur"
    REDACTION = "redaction"


class TaskContext(Strict):
    tenant_id: UUID | None
    matter_id: UUID | None
    legal_as_of: date
    territory: str | None
    #: Sous-traitants autorisés par le tenant pour recevoir des données client.
    authorized_processors: list[str] = Field(default_factory=list)
    budget_remaining_micro_eur: int | None = Field(default=None, ge=0)


class ComplexityAssessment(Strict):
    level: Literal["SIMPLE", "INTERMEDIAIRE", "COMPLEXE"]
    signals: list[str] = Field(description="Indices observés justifiant le niveau")
    requires_case_law: bool
    requires_procedure: bool
    requires_documents: bool


class RoutingDecision(Strict):
    assessment: ComplexityAssessment
    agents: list[AgentName] = Field(description="Agents retenus, dans l'ordre d'exécution")
    skipped: dict[str, str] = Field(description="Agent écarté -> motif")


class Claim(Strict):
    """Affirmation produite par un agent, toujours typée et rattachée à ses sources."""

    kind: ClaimKind
    statement: str = Field(min_length=1, max_length=4000)
    citations: list[SourceReference] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    support: SupportStatus
    uncertainty: str | None = None


class AgentTask(Strict):
    task_id: UUID
    trace_id: UUID
    agent: AgentName
    agent_contract_version: str
    context: TaskContext
    instruction: str = Field(max_length=8000)
    #: Résultats des agents amont, transmis tels quels (jamais reformulés).
    inputs: list[AgentResult] = Field(default_factory=list)


class AgentUsage(Strict):
    provider: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    calls: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    estimated_cost_micro_eur: int = Field(ge=0)


class AgentResult(Strict):
    task_id: UUID
    agent: AgentName
    agent_version: str
    status: Literal["OK", "PARTIEL", "ECHEC", "BLOQUE"]
    claims: list[Claim]
    verifications: list[CitationVerification] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    usage: list[AgentUsage] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime


AgentTask.model_rebuild()
