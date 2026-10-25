"""Évaluation du pipeline sur le corpus de cas techniques (non validés juridiquement)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
import pytest

from avocat_expert.evaluation.runner import load_cases, run
from avocat_expert.verification.lexverif import LexverifEngine

from .conftest import REPO_ROOT

pytestmark = [pytest.mark.db, pytest.mark.engine]

#: Échecs connus et documentés (docs/phases/phase-A-rapport.md). Toute
#: variation, amélioration comprise, doit être constatée et documentée.
#: Sans canal sémantique : SEED-014, reformulation « combien de temps » / « durée ».
KNOWN_FAILURES = {"SEED-014"}


def test_seed_corpus(conn: psycopg.Connection[Any], lexverif_bin: str) -> None:
    report = run(conn, LexverifEngine(lexverif_bin), load_cases(REPO_ROOT / "eval" / "cases" / "seed_v0.jsonl"))
    assert report["cas"] == 16
    assert report["cas_valides_juridiquement"] == 0  # aucune validation par un professionnel à ce jour
    assert report["cas_revus_par_ia_sur_delegation"] == 16
    # 19 citations sur 20 : la 20e (art. 289 CGI, citation parasite de SEED-016 sur
    # « abrogé ») a une fin non fixée par la source ; au 2026-10-24, lendemain de la
    # date de connaissance, son applicabilité est à juste titre INDETERMINEE.
    assert report["citations"]["integrite_controles_deterministes"] == 0.95
    assert report["citations"]["conformite_temporelle"] == 1.0
    assert report["citations"]["integrite_structurelle_des_extraits"] == 1.0
    assert report["blocages"]["exactitude"] == 1.0
    # Plancher de non-régression : 0,7949 mesuré après SRCH-04 sur 40 articles ;
    # 0,7821 depuis l'ajout de 3 articles aux fixtures (citation parasite ci-dessus).
    assert report["recherche"]["precision_moyenne"] >= 0.78
    assert {e["id"] for e in report["echecs"]} == KNOWN_FAILURES


@pytest.mark.search
def test_seed_corpus_with_opensearch(conn: psycopg.Connection[Any], lexverif_bin: str, opensearch_url: str) -> None:
    import uuid

    from avocat_expert.search import indexer
    from avocat_expert.search.opensearch import OpenSearchClient, OpenSearchLexicalSearcher
    from avocat_expert.storage.corpus import CorpusRepository

    client = OpenSearchClient(opensearch_url)
    alias = f"avx-eval-{uuid.uuid4().hex[:8]}"
    indexer.rebuild(conn, client, alias)
    try:
        lexical = OpenSearchLexicalSearcher(client, alias, CorpusRepository(conn))
        report = run(
            conn,
            LexverifEngine(lexverif_bin),
            load_cases(REPO_ROOT / "eval" / "cases" / "seed_v0.jsonl"),
            lexical=lexical,
        )
    finally:
        for physical in client.request("GET", f"/_alias/{alias}", ok_missing=True) or {}:
            client.request("DELETE", f"/{physical}", ok_missing=True)
    # Mesuré le 2026-10-25 : mêmes rappel et MRR que BM25 SQL, précision 0,7949
    # (la citation parasite art. 289 CGI n'est plus retenue).
    assert report["citations"]["integrite_controles_deterministes"] == 1.0
    assert report["citations"]["conformite_temporelle"] == 1.0
    assert report["blocages"]["exactitude"] == 1.0
    assert report["recherche"]["rappel_moyen"] >= 0.92
    assert report["recherche"]["precision_moyenne"] >= 0.79
    assert {e["id"] for e in report["echecs"]} == KNOWN_FAILURES


@pytest.mark.search
@pytest.mark.embedding
def test_seed_corpus_with_semantic_channel(
    conn: psycopg.Connection[Any], lexverif_bin: str, opensearch_url: str, embedding_model_dir: Path
) -> None:
    import uuid

    from avocat_expert.embedding.models import MULTILINGUAL_E5_BASE
    from avocat_expert.embedding.onnx import OnnxEmbedder
    from avocat_expert.embedding.store import compute_missing
    from avocat_expert.search import indexer
    from avocat_expert.search.opensearch import OpenSearchClient, OpenSearchLexicalSearcher, OpenSearchSemanticSearcher
    from avocat_expert.storage.corpus import CorpusRepository

    embedder = OnnxEmbedder(MULTILINGUAL_E5_BASE, embedding_model_dir)
    compute_missing(conn, embedder)
    client = OpenSearchClient(opensearch_url)
    alias = f"avx-eval-{uuid.uuid4().hex[:8]}"
    indexer.rebuild(conn, client, alias, embedding=embedder.spec)
    try:
        repository = CorpusRepository(conn)
        report = run(
            conn,
            LexverifEngine(lexverif_bin),
            load_cases(REPO_ROOT / "eval" / "cases" / "seed_v0.jsonl"),
            lexical=OpenSearchLexicalSearcher(client, alias, repository),
            semantic=OpenSearchSemanticSearcher(client, alias, repository, embedder),
        )
    finally:
        for physical in client.request("GET", f"/_alias/{alias}", ok_missing=True) or {}:
            client.request("DELETE", f"/{physical}", ok_missing=True)
    # Mesuré le 2026-10-25 (multilingual-e5-base, marge 0,015) : rappel 1,0,
    # précision 0,8205 (0,8077 en lexical seul) ; SEED-014 (« combien de temps »
    # / « durée ») aboutit par proximité de sens.
    assert report["citations"]["integrite_controles_deterministes"] == 1.0
    assert report["citations"]["conformite_temporelle"] == 1.0
    assert report["blocages"]["exactitude"] == 1.0
    assert report["recherche"]["rappel_moyen"] == 1.0
    assert report["recherche"]["precision_moyenne"] >= 0.82
    assert report["echecs"] == []
