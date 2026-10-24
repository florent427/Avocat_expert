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
    original = ingest_module._Store.store
    calls = {"n": 0}

    def failing(self: Any, item: Any) -> str:
        calls["n"] += 1
        if calls["n"] == 25:
            raise ConnectionError("coupure simulée")
        return original(self, item)

    monkeypatch.setattr(ingest_module._Store, "store", failing)
    with pytest.raises(ConnectionError):
        ingest_legi(conn, archive, batch_size=10)
    failed = conn.execute(
        "SELECT id, status, files_committed, last_committed_path FROM ingestion_run ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    assert failed is not None and failed[1:3] == ("FAILED", 20)  # deux lots validés, le troisième annulé

    monkeypatch.setattr(ingest_module._Store, "store", original)
    run_id, stats = ingest_legi(conn, archive, batch_size=10)
    assert run_id == failed[0]
    assert stats.files_seen == FIXTURE_FILES and stats.unchanged == FIXTURE_FILES
    row = conn.execute("SELECT status, resume_count, files_committed FROM ingestion_run WHERE id = %s", (run_id,))
    assert row.fetchone() == ("SUCCEEDED", 1, FIXTURE_FILES)


def test_inconsistent_resume_point_is_refused(
    conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _tar(legi_fixtures, tmp_path)

    def failing(self: Any, item: Any) -> str:
        raise ConnectionError("coupure simulée")

    original = ingest_module._Store.store
    monkeypatch.setattr(ingest_module._Store, "store", failing)
    with pytest.raises(ConnectionError):
        ingest_legi(conn, archive, batch_size=10)
    monkeypatch.setattr(ingest_module._Store, "store", original)
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


def test_same_article_twice_in_one_batch(conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path) -> None:
    # Changement de branche livré avec l'ancien fichier dans le même lot : l'ordre
    # de lecture fait foi, la seconde lecture remplace la première.
    official_id = "LEGIARTI000006792617"
    source = next(legi_fixtures.rglob(f"{official_id}.xml"))
    relative = source.relative_to(legi_fixtures).as_posix()
    for branch in ("code_et_TNC_en_vigueur/code_en_vigueur", "code_et_TNC_non_vigueur/code_non_vigueur"):
        target = tmp_path / relative.replace("code_et_TNC_en_vigueur/code_en_vigueur", branch)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
    _, stats = ingest_legi(conn, tmp_path, enforce_order=False, batch_size=100)
    assert (stats.unchanged, stats.superseded) == (1, 1)
    current = conn.execute(
        "SELECT source_path FROM provision_version WHERE official_id = %s AND sys_to IS NULL", (official_id,)
    ).fetchone()
    assert current is not None and "code_non_vigueur" in current[0]
    _, stats = ingest_legi(conn, legi_fixtures)  # restauration
    assert stats.superseded == 1


def test_newest_copy_wins_within_one_delivery(
    conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path
) -> None:
    # Stock du 2025-07-13 : 12 143 articles présents dans les deux branches. La
    # copie la plus récente (horodatage du fichier dans l'archive) fait foi, même
    # si l'ancienne copie est lue après elle.
    import io

    official_id = "LEGIARTI000006792617"
    source = next(legi_fixtures.rglob(f"{official_id}.xml"))
    data = source.read_bytes()
    relative = "20990101-000000/" + source.relative_to(legi_fixtures).as_posix()
    newer = relative.replace("code_et_TNC_en_vigueur/code_en_vigueur", "code_et_TNC_non_vigueur/code_non_vigueur")
    archive = tmp_path / "livraison-de-test.tar.gz"  # non horodatée : ne déplace pas la date de connaissance
    with tarfile.open(archive, "w:gz") as tar:
        for name, mtime in ((newer, 1_711_911_554), (relative, 1_711_052_384)):  # récent lu en premier
            info = tarfile.TarInfo(name)
            info.size, info.mtime = len(data), mtime
            tar.addfile(info, io.BytesIO(data))
    _, stats = ingest_legi(conn, archive, enforce_order=False)
    assert (stats.superseded, stats.stale_duplicate) == (1, 1)
    current = conn.execute(
        "SELECT source_path, source_mtime IS NOT NULL FROM provision_version WHERE official_id = %s AND sys_to IS NULL",
        (official_id,),
    ).fetchone()
    assert current is not None and "code_non_vigueur" in current[0] and current[1]
    _, stats = ingest_legi(conn, legi_fixtures, enforce_order=False)  # restauration
    assert stats.superseded == 1
