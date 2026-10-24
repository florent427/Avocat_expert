"""Période de validité juridique (intervalle semi-ouvert [début, fin)).

Une source peut annoncer une entrée en vigueur ou une fin à une date qui n'est
pas encore fixée (LEGI : sentinelle 2222-02-22, accompagnée de NOTA du type
« maintenues en vigueur jusqu'à leur reprise par les mesures réglementaires »).
Une telle date n'est jamais traitée comme une date réelle : l'applicabilité
n'est connue que jusqu'à la date de connaissance du corpus (dernière livraison
intégrée) et reste indéterminée au-delà.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator


class InForce(StrEnum):
    OUI = "OUI"
    NON = "NON"
    INDETERMINE = "INDETERMINE"


class LegalPeriod(BaseModel):
    """Période d'application d'une version.

    * ``valid_from=None`` : entrée en vigueur à une date non fixée par la source ;
    * ``valid_to=None`` et ``end_undetermined=False`` : pas de fin connue ;
    * ``end_undetermined=True`` : fin (abrogation) à une date non fixée.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid_from: date | None
    valid_to: date | None
    end_undetermined: bool = False

    @model_validator(mode="after")
    def _coherent(self) -> LegalPeriod:
        if self.end_undetermined and self.valid_to is not None:
            raise ValueError("fin non fixée incompatible avec une date de fin")
        return self

    @property
    def start_undetermined(self) -> bool:
        return self.valid_from is None

    @property
    def ever_in_force(self) -> bool:
        """Faux pour les versions mort-nées (fin antérieure ou égale au début)."""
        if self.valid_from is None or self.valid_to is None:
            return True
        return self.valid_to > self.valid_from

    def in_force_at(self, at: date, knowledge_date: date | None) -> InForce:
        known = knowledge_date is not None and at <= knowledge_date
        if self.valid_to is not None and at >= self.valid_to:
            return InForce.NON
        if self.valid_from is None:
            return InForce.NON if known else InForce.INDETERMINE
        if not self.ever_in_force or at < self.valid_from:
            return InForce.NON
        if self.end_undetermined and not known:
            return InForce.INDETERMINE
        return InForce.OUI
