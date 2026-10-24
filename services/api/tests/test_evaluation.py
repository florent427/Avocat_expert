"""Évaluation du pipeline sur le corpus de cas techniques (non validés juridiquement)."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from avocat_expert.evaluation.runner import load_cases, run
from avocat_expert.verification.lexverif import LexverifEngine

from .conftest import REPO_ROOT

pytestmark = [pytest.mark.db, pytest.mark.engine]

#: Échecs connus et documentés (docs/phases/phase-A-rapport.md). Toute
#: variation, amélioration comprise, doit être constatée et documentée.
KNOWN_FAILURES = {"SEED-014"}  # reformulation « combien de temps » / « durée » : canal sémantique absent


def test_seed_corpus(conn: psycopg.Connection[Any], lexverif_bin: str) -> None:
    report = run(conn, LexverifEngine(lexverif_bin), load_cases(REPO_ROOT / "eval" / "cases" / "seed_v0.jsonl"))
    assert report["cas"] == 16
    assert report["cas_valides_juridiquement"] == 0  # aucune validation par un professionnel à ce jour
    assert report["cas_revus_par_ia_sur_delegation"] == 16
    assert report["citations"]["integrite_controles_deterministes"] == 1.0
    assert report["citations"]["conformite_temporelle"] == 1.0
    assert report["citations"]["integrite_structurelle_des_extraits"] == 1.0
    assert report["blocages"]["exactitude"] == 1.0
    # Plancher de non-régression (0,7949 mesuré le 2026-10-24 après SRCH-04).
    assert report["recherche"]["precision_moyenne"] >= 0.79
    assert {e["id"] for e in report["echecs"]} == KNOWN_FAILURES
