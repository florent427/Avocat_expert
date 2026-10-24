"""Exécute un corpus de cas (JSONL) et calcule des métriques séparées.

Les métriques sont techniques : elles ne remplacent jamais la validation
juridique par un professionnel.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import psycopg
from pydantic import BaseModel, ConfigDict

from avocat_expert.answer.extractive import ExtractiveAnswerService
from avocat_expert.config import get_settings
from avocat_expert.contracts.common import CheckOutcome, SupportStatus
from avocat_expert.contracts.services import AnswerRequest, SourcedAnswer
from avocat_expert.search.excerpt import ELISION, is_item
from avocat_expert.search.ports import DisabledSemanticSearcher
from avocat_expert.search.service import HybridSearchService, PostgresLexicalSearcher
from avocat_expert.storage.corpus import CorpusRepository
from avocat_expert.verification.lexverif import CitationVerifier, LexverifEngine

DETERMINISTIC_CHECKS = ("SOURCE_IDENTIFIEE", "IDENTIFIANT_RESOLU", "PASSAGE_PRESENT", "APPLICABILITE_TEMPORELLE")


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["sources", "blocage"]
    official_ids: list[str] = []
    incertitude_contient: str | None = None


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    par: str
    date: date
    decision: Literal["valide", "a_corriger", "conteste"]
    commentaire: str


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    categorie: str
    question: str
    as_of: date
    attendu: Expected
    #: VALIDE est réservé à une validation par un professionnel du droit ;
    #: AVIS_IA_DELEGUE = revue par Claude sur délégation du référent juridique.
    validation_juridique: Literal["NON_VALIDE", "AVIS_IA_DELEGUE", "VALIDE", "CONTESTE"]
    auteur: str
    revue: Review | None = None


@dataclass
class CaseResult:
    case: Case
    passed: bool
    cited: list[str]
    reciprocal_rank: float = 0.0
    recall: float = 0.0
    precision: float = 0.0
    citations_total: int = 0
    citations_intact: int = 0
    citations_in_force: int = 0
    citations_structured: int = 0
    notes: list[str] = field(default_factory=list)


def structurally_complete(quote: str) -> bool:
    """Un extrait ne commence pas par un item d'énumération et ne s'arrête pas
    sur une phrase introductive (« … : ») privée de sa suite."""
    lines = [line for line in quote.split("\n") if line.strip() and line != ELISION]
    return bool(lines) and not is_item(lines[0]) and not lines[-1].rstrip().endswith(":")


def load_cases(path: Path) -> list[Case]:
    return [Case.model_validate_json(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def evaluate_case(case: Case, answer: SourcedAnswer) -> CaseResult:
    cited = [s.citation.official_id for s in answer.statements if s.citation and s.support is not SupportStatus.BLOQUEE]
    result = CaseResult(case=case, passed=False, cited=cited)
    for statement in answer.statements:
        if statement.verification is None or statement.citation is None:
            continue
        result.citations_total += 1
        outcomes = {c.check: c.outcome for c in statement.verification.checks}
        if all(outcomes.get(name) is CheckOutcome.OK for name in DETERMINISTIC_CHECKS):
            result.citations_intact += 1
        if statement.quote is not None and structurally_complete(statement.quote):
            result.citations_structured += 1
        ref = statement.citation
        if (
            ref.valid_from is not None
            and ref.valid_from <= answer.as_of
            and (ref.valid_to is None or answer.as_of < ref.valid_to)
        ):
            result.citations_in_force += 1

    if case.attendu.type == "sources":
        expected = set(case.attendu.official_ids)
        found = [i for i in cited if i in expected]
        result.recall = len(set(found)) / len(expected) if expected else 0.0
        result.precision = len(found) / len(cited) if cited else 0.0
        ranks = [rank for rank, i in enumerate(cited, start=1) if i in expected]
        result.reciprocal_rank = 1.0 / ranks[0] if ranks else 0.0
        result.passed = result.recall == 1.0
    else:
        needle = case.attendu.incertitude_contient or ""
        blocked = answer.status is SupportStatus.BLOQUEE and not cited
        mentioned = any(needle in u for u in answer.uncertainties)
        result.passed = blocked and mentioned
        if not blocked:
            result.notes.append("blocage attendu non obtenu")
        if not mentioned:
            result.notes.append(f"incertitude attendue absente : {needle}")
    return result


def summarise(results: list[CaseResult]) -> dict[str, Any]:
    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    sources = [r for r in results if r.case.attendu.type == "sources"]
    blocks = [r for r in results if r.case.attendu.type == "blocage"]
    citations = sum(r.citations_total for r in results)
    by_category: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_category[r.case.categorie].append(r)
    return {
        "cas": len(results),
        "cas_valides_juridiquement": sum(r.case.validation_juridique == "VALIDE" for r in results),
        "cas_revus_par_ia_sur_delegation": sum(r.case.validation_juridique == "AVIS_IA_DELEGUE" for r in results),
        "recherche": {
            "cas": len(sources),
            "rappel_moyen": mean([r.recall for r in sources]),
            "precision_moyenne": mean([r.precision for r in sources]),
            "mrr": mean([r.reciprocal_rank for r in sources]),
        },
        "blocages": {"cas": len(blocks), "exactitude": mean([float(r.passed) for r in blocks])},
        "citations": {
            "total": citations,
            "integrite_controles_deterministes": round(sum(r.citations_intact for r in results) / citations, 4)
            if citations
            else None,
            "conformite_temporelle": round(sum(r.citations_in_force for r in results) / citations, 4)
            if citations
            else None,
            "integrite_structurelle_des_extraits": round(sum(r.citations_structured for r in results) / citations, 4)
            if citations
            else None,
        },
        "par_categorie": {
            cat: {"cas": len(rs), "reussis": sum(r.passed for r in rs)} for cat, rs in sorted(by_category.items())
        },
        "echecs": [
            {"id": r.case.id, "categorie": r.case.categorie, "cite": r.cited, "notes": r.notes}
            for r in results
            if not r.passed
        ],
    }


def run(
    conn: psycopg.Connection[Any], engine: LexverifEngine, cases: list[Case], max_sources: int = 3
) -> dict[str, Any]:
    repository = CorpusRepository(conn)
    service = ExtractiveAnswerService(
        HybridSearchService(repository, PostgresLexicalSearcher(repository), DisabledSemanticSearcher()),
        CitationVerifier(repository, engine),
    )
    today = datetime.now(UTC).date()
    results = [
        evaluate_case(
            case,
            service.answer(AnswerRequest(question=case.question, as_of=case.as_of, max_sources=max_sources), today),
        )
        for case in cases
    ]
    return summarise(results) | {"k": max_sources}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python -m avocat_expert.evaluation.runner <cas.jsonl>", file=sys.stderr)
        return 2
    settings = get_settings()
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        report = run(
            conn, LexverifEngine(settings.lexverif_bin, settings.lexverif_timeout_s), load_cases(Path(sys.argv[1]))
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
