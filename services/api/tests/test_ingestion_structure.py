"""Textes, structure et exploitation de l'ingestion LEGI (ING-01, ING-02), base réelle."""

from __future__ import annotations

import shutil
import tarfile
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest

from avocat_expert.connectors.legi import ingest as ingest_module
from avocat_expert.connectors.legi.ingest import IngestionOrderError, ResumeMismatchError, ingest_legi
from avocat_expert.storage.structure import StructureRepository

pytestmark = pytest.mark.db

KNOWLEDGE = date(2026, 10, 23)
FIXTURE_FILES = 57


def _labels(toc: Any) -> list[tuple[int, str, str]]:
    return [(depth, node.official_id, node.label) for depth, node in toc.walk() if not node.missing]


def test_table_of_contents_follows_dates(conn: psycopg.Connection[Any]) -> None:
    repo = StructureRepository(conn)
    today = repo.table_of_contents("LEGITEXT000006072050", date(2026, 10, 24), KNOWLEDGE)
    assert today is not None and today.text_version_id == "LEGITEXT000006072050"
    present = _labels(today)
    assert (3, "LEGISCTA000037388216", "Titre II : Indemnisation des travailleurs privés d'emploi") in present
    articles = [n for _, n in today.walk() if n.kind == "ARTICLE"]
    assert [(a.label, a.official_id, a.missing) for a in articles[:3]] == [
        ("L5422-1", "LEGIARTI000048590547", False),
        ("L5422-1-1", "LEGIARTI000048600619", True),  # référencé, non ingéré : lacune signalée
        ("L5422-2", "LEGIARTI000054241899", False),
    ]

    in_2010 = repo.table_of_contents("LEGITEXT000006072050", date(2010, 1, 1), KNOWLEDGE)
    assert in_2010 is not None
    titles = {node.official_id: node.label for _, node in in_2010.walk()}
    assert (
        titles["LEGISCTA000006160812"] == "Titre II : Indemnisation des travailleurs involontairement privés d'emploi"
    )
    assert "LEGISCTA000037388216" not in titles
    assert [n.official_id for _, n in in_2010.walk() if n.kind == "ARTICLE"] == [
        "LEGIARTI000019071164",  # L5422-1, version 2008-06-27 -> 2015-08-08
        "LEGIARTI000018766919",  # L5422-2, version 2008-05-01 -> 2019-01-01
    ]


def test_uncodified_text_uses_common_id(conn: psycopg.Connection[Any]) -> None:
    toc = StructureRepository(conn).table_of_contents("JORFTEXT000052102609", date(2026, 10, 24), KNOWLEDGE)
    assert toc is not None and toc.text_version_id == "LEGITEXT000052106183"
    title = conn.execute("SELECT title FROM legal_document WHERE official_id = 'JORFTEXT000052102609'").fetchone()
    assert title is not None and title[0].startswith("Décret n° 2025-822 du 12 août 2025 portant")


def test_structure_history_cannot_be_rewritten(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="insertion seule"):
        conn.execute("UPDATE structure_entry SET number = 'X' WHERE number = 'L5422-1'")
    with pytest.raises(psycopg.errors.RaiseException, match="insertion seule"):
        conn.execute("DELETE FROM structure_entry")
    with pytest.raises(psycopg.errors.RaiseException, match="modification du contenu interdite"):
        conn.execute("UPDATE document_version SET title = 'falsifié'")
    with pytest.raises(psycopg.errors.RaiseException, match="suppression interdite"):
        conn.execute("DELETE FROM structure_node_version")


def test_older_delivery_is_refused(conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path) -> None:
    older = tmp_path / "LEGI_20250101-000000"
    source = next(legi_fixtures.rglob("LEGIARTI000048590547.xml"))
    target = older / source.relative_to(legi_fixtures)
    target.parent.mkdir(parents=True)
    shutil.copy(source, target)
    runs_before = conn.execute("SELECT count(*) FROM ingestion_run").fetchone()
    with pytest.raises(IngestionOrderError, match="antérieure à la dernière livraison intégrée"):
        ingest_legi(conn, older)
    with pytest.raises(IngestionOrderError, match="non horodatée"):
        ingest_legi(conn, tmp_path)
    assert conn.execute("SELECT count(*) FROM ingestion_run").fetchone() == runs_before


def _tar(legi_fixtures: Path, tmp_path: Path) -> Path:
    archive = tmp_path / "LEGI_20261023-215041.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(legi_fixtures / "legi", arcname="20261023-215041/legi")
        tar.add(legi_fixtures / "liste_suppression_legi.dat", arcname="20261023-215041/liste_suppression_legi.dat")
    return archive


def test_streamed_archive_matches_directory(conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path) -> None:
    _, stats = ingest_legi(conn, _tar(legi_fixtures, tmp_path), batch_size=7)
    assert (stats.files_seen, stats.unchanged, stats.inserted, stats.superseded) == (FIXTURE_FILES, FIXTURE_FILES, 0, 0)
    assert stats.withdrawals_recorded == 3


def test_interrupted_ingestion_resumes_after_last_batch(
    conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _tar(legi_fixtures, tmp_path)
    original = ingest_module._Store.entry
    calls = {"n": 0}

    def failing(self: Any, entry: Any) -> str:
        calls["n"] += 1
        if calls["n"] == 25:
            raise ConnectionError("coupure simulée")
        return original(self, entry)

    monkeypatch.setattr(ingest_module._Store, "entry", failing)
    with pytest.raises(ConnectionError):
        ingest_legi(conn, archive, batch_size=10)
    failed = conn.execute(
        "SELECT id, status, files_committed, last_committed_path FROM ingestion_run ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    assert failed is not None and failed[1:3] == ("FAILED", 20)  # deux lots validés, le troisième annulé

    monkeypatch.setattr(ingest_module._Store, "entry", original)
    run_id, stats = ingest_legi(conn, archive, batch_size=10)
    assert run_id == failed[0]
    assert stats.files_seen == FIXTURE_FILES and stats.unchanged == FIXTURE_FILES
    row = conn.execute("SELECT status, resume_count, files_committed FROM ingestion_run WHERE id = %s", (run_id,))
    assert row.fetchone() == ("SUCCEEDED", 1, FIXTURE_FILES)


def test_inconsistent_resume_point_is_refused(
    conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _tar(legi_fixtures, tmp_path)

    def failing(self: Any, entry: Any) -> str:
        raise ConnectionError("coupure simulée")

    original = ingest_module._Store.entry
    monkeypatch.setattr(ingest_module._Store, "entry", failing)
    with pytest.raises(ConnectionError):
        ingest_legi(conn, archive, batch_size=10)
    monkeypatch.setattr(ingest_module._Store, "entry", original)
    # Simule un point de reprise enregistré pour une autre archive de même empreinte.
    conn.execute(
        """UPDATE ingestion_run SET files_committed = 3, last_committed_path = 'legi/autre.xml'
           WHERE id = (SELECT id FROM ingestion_run ORDER BY started_at DESC LIMIT 1)"""
    )
    with pytest.raises(ResumeMismatchError):
        ingest_legi(conn, archive, batch_size=10)
    # Le point de reprise incohérent n'est jamais réutilisé : une nouvelle ingestion complète aboutit.
    conn.execute("UPDATE ingestion_run SET files_committed = 0 WHERE status = 'FAILED'")
    _, stats = ingest_legi(conn, archive, batch_size=10)
    assert stats.files_seen == FIXTURE_FILES
