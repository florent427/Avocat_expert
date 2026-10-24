"""Cas réels du stock LEGI du 2025-07-13 (fixtures/legi/Freemium_legi_global_20250713-140000)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest

from avocat_expert.connectors.legi.archive import ArchiveReader
from avocat_expert.connectors.legi.ingest import ingest_legi
from avocat_expert.connectors.legi.parser import parse_article
from avocat_expert.connectors.legi.structure import parse_section, parse_text_structure, parse_text_version
from avocat_expert.domain.temporal import InForce

from .conftest import REPO_ROOT

STOCK = REPO_ROOT / "fixtures" / "legi" / "Freemium_legi_global_20250713-140000"
KNOWLEDGE = date(2026, 10, 23)


def _read(name: str) -> tuple[bytes, str]:
    path = next(STOCK.rglob(name))
    return path.read_bytes(), path.relative_to(STOCK).as_posix()


def test_article_without_state_or_dates_is_always_indeterminate() -> None:
    a = parse_article(*_read("LEGIARTI000006850356.xml"))
    assert (a.status, a.raw_valid_from, a.raw_valid_to) == ("", "2999-01-01", "2999-01-01")
    assert a.period.dates_unknown and a.period.valid_from is None
    for at in (date(1990, 1, 1), date(2026, 1, 1), date(2030, 1, 1)):
        assert a.period.in_force_at(at, KNOWLEDGE) is InForce.INDETERMINE


def test_unnumbered_articles_keep_distinct_identities() -> None:
    first = parse_article(*_read("LEGIARTI000029825776.xml"))
    second = parse_article(*_read("LEGIARTI000029825777.xml"))
    assert first.number == second.number == ""
    assert first.text_official_id == second.text_official_id
    assert first.unnumbered_key != second.unnumbered_key


def test_year_2222_is_an_undetermined_date() -> None:
    version = parse_text_version(*_read("texte/version/LEGITEXT000018840114.xml"))
    assert (version.status, version.raw_valid_to) == ("ABROGE_DIFF", "2222-01-01")
    assert version.period.end_undetermined and version.period.valid_to is None
    structure = parse_text_structure(*_read("texte/struct/LEGITEXT000018840114.xml"))
    assert any(e.raw_valid_to == "2222-01-01" and e.period.end_undetermined for e in structure.entries)


def test_section_without_cid_uses_text_id() -> None:
    node = parse_section(*_read("LEGISCTA000006090465.xml"))
    assert node.document_cid == "LEGITEXT000006079011"


def test_eli_index_files_are_counted_separately() -> None:
    reader = ArchiveReader(STOCK)
    kinds = sorted(e.kind for e in reader.entries())
    assert kinds == ["ARTICLE", "ARTICLE", "ARTICLE", "SECTION", "TEXT_STRUCT", "TEXT_VERSION"]
    assert (reader.eli_index, reader.ignored) == (1, 1)  # SOURCE.md


@pytest.mark.db
def test_stock_cases_are_ingested_without_rejection(conn: psycopg.Connection[Any]) -> None:
    _, stats = ingest_legi(conn, STOCK, enforce_order=False)  # stock antérieur aux fixtures déjà intégrées
    assert stats.rejected == 0, stats.errors
    assert stats.eli_index == 1
    rows = conn.execute(
        """SELECT pv.official_id, p.number, p.unnumbered_key FROM provision_version pv
           JOIN provision p ON p.id = pv.provision_id
           WHERE pv.official_id IN ('LEGIARTI000029825776', 'LEGIARTI000029825777') AND pv.sys_to IS NULL
           ORDER BY 1"""
    ).fetchall()
    assert len(rows) == 2 and rows[0][1] == rows[1][1] == "" and rows[0][2] != rows[1][2]
    unknown = conn.execute(
        "SELECT dates_unknown, valid_period = 'empty' FROM provision_version "
        "WHERE official_id = 'LEGIARTI000006850356' AND sys_to IS NULL"
    ).fetchone()
    assert unknown == (True, True)
