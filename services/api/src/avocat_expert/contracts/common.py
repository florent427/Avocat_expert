"""Types communs aux contrats."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimKind(StrEnum):
    """Nature d'une affirmation : le système ne mélange jamais ces catégories."""

    FAIT = "FAIT"
    HYPOTHESE = "HYPOTHESE"
    DROIT_APPLICABLE = "DROIT_APPLICABLE"
    INTERPRETATION = "INTERPRETATION"
    RECOMMANDATION = "RECOMMANDATION"


class SupportStatus(StrEnum):
    FONDEE = "FONDEE"
    INCERTAINE = "INCERTAINE"
    BLOQUEE = "BLOQUEE"


class CheckOutcome(StrEnum):
    OK = "OK"
    ECHEC = "ECHEC"
    INDETERMINE = "INDETERMINE"
    NON_EVALUE = "NON_EVALUE"


class Verdict(StrEnum):
    CONFORME = "CONFORME"
    INCERTAIN = "INCERTAIN"
    NON_CONFORME = "NON_CONFORME"


class SourceReference(Strict):
    """Référence traçable vers une version précise d'une source officielle."""

    source_code: str = Field(description="Code de la source, ex. DILA_LEGI")
    official_id: str = Field(description="Identifiant officiel de la version citée, ex. LEGIARTI…")
    document_official_id: str
    document_title: str
    provision_number: str
    valid_from: date | None = Field(description="None : entrée en vigueur à une date non fixée par la source")
    valid_to: date | None = Field(description="None : pas de date de fin connue (voir end_undetermined)")
    end_undetermined: bool = Field(
        default=False, description="Fin (abrogation) annoncée par la source à une date non encore fixée"
    )
    source_status: str = Field(description="Statut brut publié par la source")
    source_path: str
    source_file_sha256: str
    source_archive: str = Field(description="Nom (horodaté) de l'archive livrée par la source")
    connector_version: str
