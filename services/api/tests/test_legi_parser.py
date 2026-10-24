"""Analyse des fichiers LEGI réels (archive DILA du 2026-10-23)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from avocat_expert.connectors.legi.archive import iter_article_files, read_withdrawals
from avocat_expert.connectors.legi.parser import LegiFormatError, parse_article
from avocat_expert.domain.temporal import InForce

KNOWLEDGE = date(2026, 10, 23)  # livraison LEGI_20261023-215041


@pytest.fixture(scope="module")
def articles(legi_fixtures: Path) -> dict[str, object]:
    return {a.official_id: a for a in (parse_article(e.data, e.path) for e in iter_article_files(legi_fixtures))}


def test_all_fixtures_parse(articles: dict[str, object]) -> None:
    assert len(articles) == 43


def test_open_end_sentinel_becomes_none(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000048590547"]
    assert a.number == "L5422-1"
    assert a.status == "VIGUEUR"
    assert a.raw_valid_to == "2999-01-01"
    assert a.period.valid_from == date(2025, 1, 1)
    assert a.period.valid_to is None
    assert a.text_official_id == "LEGITEXT000006072050"
    assert a.text_title == "Code du travail"


def test_content_is_literal_with_paragraphs(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000048590547"]
    first = a.content.split("\n")[0]
    assert first.startswith("I.-Ont droit à l'allocation d'assurance les travailleurs aptes au travail")
    assert "\n1° Soit la privation d'emploi est involontaire" in a.content
    assert len(a.content_sha256) == 64


def test_section_path(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000048590547"]
    assert a.section_path[0] == "Partie législative"
    assert a.section_path[-1] == "Sous-section 1 : Conditions d'attribution."


def test_stillborn_version_never_in_force(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000048170646"]  # D251-1 code de l'énergie, MODIFIE_MORT_NE
    assert a.status == "MODIFIE_MORT_NE"
    assert a.period.valid_to is not None and a.period.valid_to < a.period.valid_from
    assert not a.period.ever_in_force


def test_deferred_version(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000053150353"]  # L161-1 CIBS, VIGUEUR_DIFF à compter de 2027
    assert a.status == "VIGUEUR_DIFF"
    assert a.period.valid_from == date(2027, 1, 1)
    assert a.period.in_force_at(date(2026, 10, 24), KNOWLEDGE) is InForce.NON
    assert a.period.in_force_at(date(2027, 1, 1), KNOWLEDGE) is InForce.OUI


def test_undetermined_end_date_is_not_a_real_date(articles: dict) -> None:  # type: ignore[type-arg]
    # Article 289 du CGI : abrogation différée « jusqu'à leur reprise par les mesures
    # réglementaires » (NOTA). Avant correction, la fin était lue comme le 22/02/2222
    # et l'article déclaré en vigueur avec certitude en 2030.
    a = articles["LEGIARTI000048827413"]
    assert (a.status, a.raw_valid_to) == ("ABROGE_DIFF", "2222-02-22")
    assert a.period.valid_to is None and a.period.end_undetermined
    assert a.period.in_force_at(date(2026, 1, 1), KNOWLEDGE) is InForce.OUI
    assert a.period.in_force_at(date(2030, 1, 1), KNOWLEDGE) is InForce.INDETERMINE
    assert a.period.in_force_at(date(2026, 1, 1), None) is InForce.INDETERMINE


def test_undetermined_start_date(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000025453562"]  # MODIFIE_MORT_NE, DATE_DEBUT 2222-02-22
    assert a.raw_valid_from == "2222-02-22"
    assert a.period.valid_from is None and a.period.start_undetermined
    assert a.period.in_force_at(date(2026, 1, 1), KNOWLEDGE) is InForce.NON


def test_section_title_is_chosen_at_version_date(articles: dict) -> None:  # type: ignore[type-arg]
    # L'intitulé du titre II a changé le 2019-01-01 ; la version de 2008 de
    # L5422-1 doit porter l'intitulé alors en vigueur.
    old = articles["LEGIARTI000006903823"]
    assert "Titre II : Indemnisation des travailleurs involontairement privés d'emploi" in old.section_path
    current = articles["LEGIARTI000048590547"]
    assert "Titre II : Indemnisation des travailleurs privés d'emploi" in current.section_path


def test_declared_versions_and_links(articles: dict) -> None:  # type: ignore[type-arg]
    a = articles["LEGIARTI000051831141"]
    ids = [v.official_id for v in a.declared_versions]
    assert "LEGIARTI000049133395" in ids  # version déclarée, absente des fixtures
    assert {link.link_type for link in a.links} == {"CITATION", "MODIFIE"}


def test_withdrawal_list(legi_fixtures: Path) -> None:
    withdrawals = read_withdrawals(legi_fixtures)
    assert [w.official_id for w in withdrawals] == [
        "LEGIARTI000006309101",
        "LEGIARTI000055010442",
        "LEGIARTI000055010444",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b"<ARTICLE><META>",
        b"<TEXTE/>",
        b"<ARTICLE><META><META_COMMUN><ID>LEGIARTI000000000001</ID></META_COMMUN></META></ARTICLE>",
        b"<ARTICLE><META><META_COMMUN><ID>FAKE</ID></META_COMMUN></META></ARTICLE>",
    ],
)
def test_malformed_files_are_rejected(payload: bytes) -> None:
    with pytest.raises(LegiFormatError):
        parse_article(payload, "test.xml")


def test_entity_expansion_is_refused() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "xxxxxxxxxx"><!ENTITY y "&x;&x;&x;&x;&x;">]>'
        b"<ARTICLE>&y;</ARTICLE>"
    )
    with pytest.raises(Exception, match=r"(?i)entit"):
        parse_article(bomb, "bomb.xml")


def test_external_entity_is_refused() -> None:
    xxe = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e SYSTEM "file:///etc/passwd">]><ARTICLE>&e;</ARTICLE>'
    with pytest.raises(Exception, match=r"(?i)entit"):
        parse_article(xxe, "xxe.xml")


def test_streamed_tar_reading_with_many_members(legi_fixtures: Path, tmp_path: Path) -> None:
    import io
    import tarfile

    from avocat_expert.connectors.legi.archive import ArchiveReader

    data = next(legi_fixtures.rglob("LEGIARTI000048590547.xml")).read_bytes()
    archive = tmp_path / "LEGI_20990101-000000.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for i in range(3000):
            info = tarfile.TarInfo(f"x/legi/global/a/article/LEGI/ARTI/{i:06d}/LEGIARTI{i:012d}.xml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        info = tarfile.TarInfo("x/legi/global/README")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"ok"))
    reader = ArchiveReader(archive)
    entries = list(reader.entries())
    assert len(entries) == 3000 and reader.ignored == 1
    assert entries[-1].path == "legi/global/a/article/LEGI/ARTI/002999/LEGIARTI000000002999.xml"
