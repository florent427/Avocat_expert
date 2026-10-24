"""Période de validité juridique (intervalle semi-ouvert [début, fin))."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class LegalPeriod(BaseModel):
    """Période d'application d'une version. ``valid_to=None`` : pas de fin connue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid_from: date
    valid_to: date | None

    @property
    def ever_in_force(self) -> bool:
        return self.valid_to is None or self.valid_to > self.valid_from

    def in_force_at(self, at: date) -> bool:
        if not self.ever_in_force or at < self.valid_from:
            return False
        return self.valid_to is None or at < self.valid_to
