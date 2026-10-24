"""Analyse des fichiers réels de textes et de structure LEGI (livraison DILA du 2026-10-23)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from avocat_expert.connectors.legi.parser import LegiFormatError
from avocat_expert.connectors.legi.structure import parse_section, parse_text_structure, parse_text_version


def _file(fixtures: Path, pattern: str) -> tuple[bytes, str]:
    path = next(fixtures.rglob(pattern))
    return path.read_bytes(), path.relative_to(fixtures).as_posix()


def test_code_text_version(legi_fixtures: Path) -> None:
    t = parse_text_version(*_file(legi_fixtures, "texte/version/LEGITEXT000006072050.xml"))
    assert (t.official_id, t.document_cid, t.nature) == ("LEGITEXT000006072050", "LEGITEXT000006072050", "CODE")
    assert t.title == "Code du travail"
    # DATE_PUBLI / DATE_TEXTE = 2999-01-01 pour un code : absence de date, valeur brute conservée.
    assert t.publication_date is None and t.raw_publication_date == "2999-01-01"


def test_decree_text_version(legi_fixtures: Path) -> None:
    t = parse_text_version(*_file(legi_fixtures, "texte/version/LEGITEXT000052106183.xml"))
    # Texte non codifié : identifiant commun JORFTEXT, version LEGITEXT.
    assert (t.document_cid, t.official_id) == ("JORFTEXT000052102609", "LEGITEXT000052106183")
    assert (t.nature, t.number, t.nor) == ("DECRET", "2025-822", "APFF2517870D")
    assert (t.publication_date, t.signature_date) == (date(2025, 8, 15), date(2025, 8, 12))
    assert t.period.valid_from == date(2025, 12, 1) and t.period.valid_to is None
    assert t.title_full is not None and t.title_full.startswith("Décret n° 2025-822 du 12 août 2025 portant")
    assert t.visas is not None and t.visas.startswith("Le Premier ministre,")
    assert t.publication_origin == "JORF n°0189 du 15 août 2025"
    assert any(link.target_official_id == "LEGIARTI000037374022" for link in t.links)  # C. trav. L6113-1


def test_text_structure_versions_and_plan(legi_fixtures: Path) -> None:
    node = parse_text_structure(*_file(legi_fixtures, "texte/struct/LEGITEXT000052106183.xml"))
    versions = [e for e in node.entries if e.kind == "VERSION_TEXTE"]
    plan = [e for e in node.entries if e.kind == "SECTION"]
    assert [(v.target_official_id, v.status) for v in versions] == [
        ("JORFTEXT000052102609", ""),  # version JORF d'origine : état vide, dates 2999-01-01
        ("LEGITEXT000052106183", "VIGUEUR"),
    ]
    assert versions[0].period.valid_from is None  # « 2999-01-01 » n'est pas une date réelle
    assert plan and all(e.level == 1 for e in plan)
    assert [e.position for e in node.entries] == list(range(len(node.entries)))


def test_section_entries_and_context(legi_fixtures: Path) -> None:
    node = parse_section(*_file(legi_fixtures, "LEGISCTA000006195891.xml"))
    assert node.kind == "SECTION" and node.document_cid == "LEGITEXT000006072050"
    assert node.title == "Sous-section 1 : Conditions d'attribution."
    first = node.entries[0]
    assert (first.kind, first.target_official_id, first.number, first.status) == (
        "ARTICLE",
        "LEGIARTI000006903823",
        "L5422-1",
        "MODIFIE",
    )
    assert (first.period.valid_from, first.period.valid_to) == (date(2008, 5, 1), date(2008, 6, 27))
    assert len(node.entries) == 16
    # Contexte : six niveaux ; le titre II porte deux intitulés successifs datés.
    assert len(node.context) == 6
    titre_ii = node.context[3]
    assert [(t.section_id, t.raw_valid_from, t.raw_valid_to) for t in titre_ii] == [
        ("LEGISCTA000006160812", "2008-05-01", "2019-01-01"),
        ("LEGISCTA000037388216", "2019-01-01", "2999-01-01"),
    ]


def test_section_id_must_match_file_name(legi_fixtures: Path) -> None:
    data, path = _file(legi_fixtures, "LEGISCTA000006195891.xml")
    with pytest.raises(LegiFormatError, match="différent du nom de fichier"):
        parse_section(data, path.replace("LEGISCTA000006195891", "LEGISCTA000099999999"))


def test_unexpected_structure_element_is_rejected(legi_fixtures: Path) -> None:
    data, path = _file(legi_fixtures, "LEGISCTA000006195891.xml")
    with pytest.raises(LegiFormatError, match="élément de structure inattendu"):
        parse_section(data.replace(b"<STRUCTURE_TA>", b"<STRUCTURE_TA><SCRIPT/>"), path)
