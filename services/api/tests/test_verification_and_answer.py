"""Chaîne complète : corpus réel -> recherche -> réponse extractive -> vérification Rust."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import date
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from avocat_expert.answer.extractive import ExtractiveAnswerService
from avocat_expert.contracts.common import CheckOutcome, SupportStatus, Verdict
from avocat_expert.contracts.services import AnswerRequest
from avocat_expert.search.ports import DisabledSemanticSearcher
from avocat_expert.search.service import HybridSearchService, PostgresLexicalSearcher
from avocat_expert.storage.corpus import CorpusRepository
from avocat_expert.verification.lexverif import CitationVerifier, LexverifEngine

pytestmark = [pytest.mark.db, pytest.mark.engine]

TODAY = date(2026, 10, 24)
L5422_1_OPENING = (
    "I.-Ont droit à l'allocation d'assurance les travailleurs aptes au travail et recherchant un emploi "
    "qui satisfont à des conditions d'âge et d'activité antérieure"
)


@pytest.fixture
def verifier(conn: psycopg.Connection[Any], lexverif_bin: str) -> CitationVerifier:
    return CitationVerifier(CorpusRepository(conn), LexverifEngine(lexverif_bin))


@pytest.fixture
def answer_service(conn: psycopg.Connection[Any], verifier: CitationVerifier) -> ExtractiveAnswerService:
    repo = CorpusRepository(conn)
    return ExtractiveAnswerService(
        HybridSearchService(repo, PostgresLexicalSearcher(repo), DisabledSemanticSearcher()), verifier
    )


def _outcomes(result: Any) -> dict[str, CheckOutcome]:
    return {c.check: c.outcome for c in result.checks}


def test_exact_quote_passes_deterministic_checks(verifier: CitationVerifier) -> None:
    result = verifier.verify("LEGIARTI000048590547", L5422_1_OPENING, TODAY, None)
    outcomes = _outcomes(result)
    assert outcomes["SOURCE_IDENTIFIEE"] is CheckOutcome.OK
    assert outcomes["IDENTIFIANT_RESOLU"] is CheckOutcome.OK
    assert outcomes["PASSAGE_PRESENT"] is CheckOutcome.OK
    assert outcomes["APPLICABILITE_TEMPORELLE"] is CheckOutcome.OK
    # LEGI ne renseigne pas le champ territorial : jamais présumé.
    assert outcomes["TERRITOIRE"] is CheckOutcome.INDETERMINE
    assert outcomes["ADEQUATION_RAISONNEMENT"] is CheckOutcome.NON_EVALUE
    assert result.verdict is Verdict.INCERTAIN
    assert result.quote_start == 0


def test_quote_with_typographic_variants_still_matches(verifier: CitationVerifier) -> None:
    variant = L5422_1_OPENING.replace("'", "’").replace(" ", " ", 3)
    assert (
        _outcomes(verifier.verify("LEGIARTI000048590547", variant, TODAY, None))["PASSAGE_PRESENT"] is CheckOutcome.OK
    )


def test_altered_quote_is_rejected(verifier: CitationVerifier) -> None:
    altered = L5422_1_OPENING.replace("aptes au travail", "inaptes au travail")
    result = verifier.verify("LEGIARTI000048590547", altered, TODAY, None)
    assert _outcomes(result)["PASSAGE_PRESENT"] is CheckOutcome.ECHEC
    assert result.verdict is Verdict.NON_CONFORME


def test_outdated_version_is_rejected_and_replacement_named(verifier: CitationVerifier) -> None:
    # Version 2022-12-23 -> 2025-01-01 citée pour une date de 2026.
    result = verifier.verify(
        "LEGIARTI000046774640", "I.-Ont droit à l'allocation d'assurance les travailleurs", TODAY, None
    )
    assert _outcomes(result)["APPLICABILITE_TEMPORELLE"] is CheckOutcome.ECHEC
    assert result.version_in_force_at_date == "LEGIARTI000048590547"
    assert result.verdict is Verdict.NON_CONFORME


def test_fictitious_identifier_is_rejected(verifier: CitationVerifier) -> None:
    result = verifier.verify("LEGIARTI000099999999", L5422_1_OPENING, TODAY, None)
    assert _outcomes(result)["IDENTIFIANT_RESOLU"] is CheckOutcome.ECHEC
    assert result.verdict is Verdict.NON_CONFORME


def test_malformed_identifier_is_rejected(verifier: CitationVerifier) -> None:
    result = verifier.verify("Code du travail, art. L5422-1", L5422_1_OPENING, TODAY, None)
    assert _outcomes(result)["SOURCE_IDENTIFIEE"] is CheckOutcome.ECHEC
    assert result.verdict is Verdict.NON_CONFORME


def test_deferred_provision_not_applicable_yet(verifier: CitationVerifier, conn: psycopg.Connection[Any]) -> None:
    version = CorpusRepository(conn).get_current_version("LEGIARTI000053150353")  # CIBS L161-1, 2027
    assert version is not None
    quote = version.text_content.split("\n")[0]
    assert verifier.verify(version.official_id, quote, TODAY, None).verdict is Verdict.NON_CONFORME
    assert verifier.verify(version.official_id, quote, date(2027, 1, 1), None).verdict is Verdict.INCERTAIN


def test_answer_cites_in_force_version(answer_service: ExtractiveAnswerService) -> None:
    answer = answer_service.answer(
        AnswerRequest(question="Quelles sont les conditions d'attribution de l'allocation d'assurance chômage ?"), TODAY
    )
    assert answer.mode == "EXTRACTIF"
    assert answer.statements, "au moins une disposition attendue"
    for statement in answer.statements:
        assert statement.citation is not None
        assert statement.citation.valid_from is not None and statement.citation.valid_from <= TODAY
        assert statement.citation.valid_to is None or statement.citation.valid_to > TODAY
        assert statement.verification is not None
        assert statement.support is not SupportStatus.BLOQUEE
        assert statement.quote is not None
    assert "LEGIARTI000048590547" in [s.citation.official_id for s in answer.statements if s.citation]
    assert answer.status is SupportStatus.INCERTAINE  # territoire non qualifié par la source
    assert "consultation juridique" in answer.disclaimer


def test_answer_at_past_date_uses_historical_version(answer_service: ExtractiveAnswerService) -> None:
    answer = answer_service.answer(
        AnswerRequest(
            question="article L. 125-2 du code des assurances catastrophes naturelles", as_of=date(2000, 1, 1)
        ),
        TODAY,
    )
    ids = [s.citation.official_id for s in answer.statements if s.citation]
    assert ids[0] == "LEGIARTI000006792615"


def test_fictitious_article_produces_no_answer(answer_service: ExtractiveAnswerService) -> None:
    answer = answer_service.answer(AnswerRequest(question="article L. 9999-99 zzzqqq"), TODAY)
    assert answer.status is SupportStatus.BLOQUEE
    assert answer.statements == []
    assert any("L9999-99" in u for u in answer.uncertainties)


def test_coverage_gap_is_surfaced(answer_service: ExtractiveAnswerService) -> None:
    answer = answer_service.answer(
        AnswerRequest(question="article D. 251-1 du code de l'énergie", as_of=date(2024, 6, 1)), TODAY
    )
    assert answer.status is SupportStatus.BLOQUEE
    assert any("LEGIARTI000049133395" in u for u in answer.uncertainties)


TOKEN = "jeton-e2e-non-secret"


@pytest.fixture
def api_client(ingested_url: str, lexverif_bin: str) -> Iterator[TestClient]:
    from avocat_expert.api.app import create_app
    from avocat_expert.config import Settings, get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=ingested_url,
        lexverif_bin=lexverif_bin,
        dev_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
    )
    with TestClient(app) as client:
        yield client


def test_api_answer_end_to_end_and_trace_without_question_text(
    api_client: TestClient, conn: psycopg.Connection[Any]
) -> None:
    question = "Durée d'indemnisation de l'allocation d'assurance selon l'âge"
    response = api_client.post(
        "/v1/answer", json={"question": question, "as_of": "2026-10-24"}, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["statements"]
    assert body["search"]["channels"][3] == {
        "channel": "semantique",
        "enabled": False,
        "detail": "désactivé : aucun modèle d'embeddings configuré",
    }
    digest = hashlib.sha256(question.encode()).hexdigest()
    trace = conn.execute(
        "SELECT t.input_sha256, t.input_length, u.provider, u.estimated_cost_micro_eur FROM execution_trace t "
        "JOIN usage_record u ON u.trace_id = t.id WHERE t.input_sha256 = %s",
        (digest,),
    ).fetchone()
    assert trace == (digest, len(question), "none", 0)
    leaked = conn.execute(
        "SELECT count(*) FROM execution_trace t JOIN execution_step s ON s.trace_id = t.id "
        "WHERE t.routing::text LIKE %s OR s.detail::text LIKE %s",
        ("%indemnisation%", "%indemnisation%"),
    ).fetchone()
    assert leaked == (0,)


def test_api_verify_endpoint(api_client: TestClient) -> None:
    response = api_client.post(
        "/v1/citations/verify",
        json={"official_id": "LEGIARTI000048590547", "quote": L5422_1_OPENING, "as_of": "2026-10-24"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    assert response.json()["verdict"] == "INCERTAIN"


@pytest.mark.parametrize("as_of", [date(2026, 10, 24), date(2027, 6, 1)])
def test_named_code_excludes_other_codes(answer_service: ExtractiveAnswerService, as_of: date) -> None:
    answer = answer_service.answer(
        AnswerRequest(question="article L. 161-1 du code des impositions sur les biens et services", as_of=as_of), TODAY
    )
    titles = {s.citation.document_title for s in answer.statements if s.citation}
    assert titles == {"Code des impositions sur les biens et services"}


def test_explicit_reference_without_content_terms_cites_only_that_article(
    answer_service: ExtractiveAnswerService,
) -> None:
    answer = answer_service.answer(AnswerRequest(question="article L. 5422-2 du code du travail"), TODAY)
    assert [s.citation.provision_number for s in answer.statements if s.citation] == ["L5422-2"]


def test_weak_lexical_matches_are_dropped(answer_service: ExtractiveAnswerService) -> None:
    answer = answer_service.answer(AnswerRequest(question="inscription sur la liste des demandeurs d'emploi"), TODAY)
    assert [s.citation.provision_number for s in answer.statements if s.citation] == ["L5411-1"]


@pytest.fixture
def least_privilege_url(ingested_url: str) -> Iterator[str]:
    """Rôle de connexion membre d'avx_app uniquement, comme l'API en production."""
    import secrets

    from psycopg import sql

    role, password = f"avx_api_test_{secrets.token_hex(4)}", secrets.token_urlsafe(16)
    with psycopg.connect(ingested_url, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE avx_app").format(
                sql.Identifier(role), sql.Literal(password)
            )
        )
    try:
        yield psycopg.conninfo.make_conninfo(ingested_url, user=role, password=password)
    finally:
        with psycopg.connect(ingested_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_api_runs_with_least_privilege_role(least_privilege_url: str, lexverif_bin: str) -> None:
    from avocat_expert.api.app import create_app
    from avocat_expert.config import Settings, get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=least_privilege_url,
        lexverif_bin=lexverif_bin,
        dev_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/answer",
            json={"question": "inscription sur la liste des demandeurs d'emploi", "as_of": "2026-10-24"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 200, response.text
    assert [s["citation"]["official_id"] for s in response.json()["statements"]] == ["LEGIARTI000048590205"]


def test_undetermined_abrogation_is_never_presented_as_certain(answer_service: ExtractiveAnswerService) -> None:
    # Art. 289 CGI : ABROGE_DIFF, fin 2222-02-22 (date non fixée). Corpus connu au 2026-10-23.
    answer = answer_service.answer(
        AnswerRequest(question="article 289 du code général des impôts", as_of=date(2030, 1, 1)), TODAY
    )
    statements = [s for s in answer.statements if s.citation and s.citation.official_id == "LEGIARTI000048827413"]
    assert len(statements) == 1
    statement = statements[0]
    assert statement.citation is not None and statement.citation.end_undetermined
    assert statement.citation.valid_to is None
    assert "date d'abrogation non encore fixée" in statement.text
    assert "2222" not in statement.text
    assert statement.support is SupportStatus.INCERTAINE
    assert statement.verification is not None
    outcomes = {c.check: c.outcome.value for c in statement.verification.checks}
    assert outcomes["APPLICABILITE_TEMPORELLE"] == "INDETERMINE"
    assert any("postérieure à la dernière livraison intégrée (2026-10-23)" in u for u in answer.uncertainties)
