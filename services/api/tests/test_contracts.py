from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from avocat_expert.contracts.agents import ComplexityAssessment, RoutingDecision
from avocat_expert.contracts.services import AnswerRequest, CitationVerificationRequest


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AnswerRequest.model_validate({"question": "Quelle durée ?", "tool": "rm -rf"})


def test_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        AnswerRequest(question="x" * 4001)
    with pytest.raises(ValidationError):
        CitationVerificationRequest.model_validate({"official_id": "X" * 65, "quote": "q", "as_of": "2026-01-01"})


def test_routing_decision_records_skipped_agents() -> None:
    decision = RoutingDecision(
        assessment=ComplexityAssessment(
            level="SIMPLE",
            signals=["question portant sur un article identifié"],
            requires_case_law=False,
            requires_procedure=False,
            requires_documents=False,
        ),
        agents=["recherche_legislative", "verificateur"],  # type: ignore[list-item]
        skipped={"jurisprudence": "non requis pour une question de texte"},
    )
    assert decision.agents[-1].value == "verificateur"


def test_exported_schemas_are_up_to_date() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "export_schemas.py"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
