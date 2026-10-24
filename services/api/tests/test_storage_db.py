"""Tests sur une base PostgreSQL réelle : migrations, ingestion bitemporelle,
immuabilité de l'historique, isolation multi-tenant (RLS)."""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest

from avocat_expert.connectors.legi.ingest import ingest_legi
from avocat_expert.storage.corpus import CorpusRepository
from avocat_expert.storage.migrate import MigrationError, apply_migrations

pytestmark = pytest.mark.db


def test_migrations_are_idempotent(conn: psycopg.Connection[Any]) -> None:
    assert apply_migrations(conn) == []


def test_modified_migration_is_detected(conn: psycopg.Connection[Any], tmp_path: Path) -> None:
    from avocat_expert.storage.migrate import MIGRATIONS_DIR

    for f in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(f, tmp_path / f.name)
    first = sorted(tmp_path.glob("0001_*.sql"))[0]
    first.write_text(first.read_text("utf-8") + "\n-- altération\n", "utf-8")
    with pytest.raises(MigrationError):
        apply_migrations(conn, tmp_path)


def test_first_ingestion_stats(conn: psycopg.Connection[Any]) -> None:
    row = conn.execute(
        "SELECT status, stats FROM ingestion_run WHERE status = 'SUCCEEDED' ORDER BY started_at LIMIT 1"
    ).fetchone()
    assert row is not None
    status, stats = row
    assert status == "SUCCEEDED"
    assert stats["files_seen"] == 43
    assert stats["inserted"] == 43
    assert stats["withdrawals_recorded"] == 3
    assert stats["withdrawals_matched"] == 0  # les articles retirés ne font pas partie des fixtures


def test_reingestion_is_idempotent(conn: psycopg.Connection[Any], legi_fixtures: Path) -> None:
    _, stats = ingest_legi(conn, legi_fixtures)
    assert (stats.inserted, stats.superseded, stats.unchanged) == (0, 0, 43)


def test_change_of_knowledge_preserves_history(
    conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path
) -> None:
    # Simule une nouvelle livraison où la date de fin d'une version change
    # (cas réel lors d'une modification législative ultérieure).
    target_id = "LEGIARTI000054241899"  # L5422-2 code du travail
    source = next(legi_fixtures.rglob(f"{target_id}.xml"))
    copy = tmp_path / "legi" / source.relative_to(legi_fixtures / "legi")
    copy.parent.mkdir(parents=True)
    content = source.read_text("utf-8")
    assert "<DATE_FIN>2999-01-01</DATE_FIN>" in content
    copy.write_text(
        content.replace("<DATE_FIN>2999-01-01</DATE_FIN>", "<DATE_FIN>2027-03-01</DATE_FIN>").replace(
            "<ETAT>VIGUEUR</ETAT>", "<ETAT>MODIFIE</ETAT>"
        ),
        "utf-8",
    )
    _, stats = ingest_legi(conn, tmp_path)
    assert stats.superseded == 1

    rows = conn.execute(
        "SELECT valid_to, source_status, sys_to IS NULL, superseded_by IS NOT NULL "
        "FROM provision_version WHERE official_id = %s ORDER BY sys_from",
        (target_id,),
    ).fetchall()
    assert rows == [(None, "VIGUEUR", False, True), (date(2027, 3, 1), "MODIFIE", True, False)]

    # Connaissance à une date système antérieure : l'ancienne ligne reste interrogeable.
    old = conn.execute(
        "SELECT count(*) FROM provision_version WHERE official_id = %s AND sys_to IS NOT NULL", (target_id,)
    ).fetchone()
    assert old == (1,)

    # Restaure l'état des fixtures pour les autres tests.
    _, stats = ingest_legi(conn, legi_fixtures)
    assert stats.superseded == 1


def test_history_cannot_be_rewritten(conn: psycopg.Connection[Any]) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="modification du contenu interdite"):
        conn.execute(
            "UPDATE provision_version SET text_content = 'falsifié' WHERE official_id = 'LEGIARTI000048590547'"
        )
    with pytest.raises(psycopg.errors.RaiseException, match="suppression interdite"):
        conn.execute("DELETE FROM provision_version WHERE official_id = 'LEGIARTI000048590547'")
    with pytest.raises(psycopg.errors.RaiseException, match="historique close"):
        conn.execute("UPDATE provision_version SET withdrawn_from_source = true WHERE sys_to IS NOT NULL")


def test_temporal_lookup(conn: psycopg.Connection[Any]) -> None:
    repo = CorpusRepository(conn)
    in_2020 = repo.find_in_force_by_number("L5422-1", date(2020, 6, 1))
    assert [v.official_id for v in in_2020] == ["LEGIARTI000037388218"]  # 2019-01-01 -> 2022-12-23
    # Borne de fin exclue : le 2022-12-23, c'est la version suivante qui s'applique.
    assert [v.official_id for v in repo.find_in_force_by_number("L5422-1", date(2022, 12, 23))] == [
        "LEGIARTI000046774640"
    ]
    today = repo.find_in_force_by_number("L5422-1", date(2026, 10, 24))
    assert [v.official_id for v in today] == ["LEGIARTI000048590547"]
    # Aucune version mort-née ni vide n'est retenue le 2023-10-10.
    assert [v.official_id for v in repo.find_in_force_by_number("D251-1", date(2023, 10, 10))] == [
        "LEGIARTI000048173002"
    ]


def test_coverage_gap_is_reported(conn: psycopg.Connection[Any]) -> None:
    repo = CorpusRepository(conn)
    assert repo.find_in_force_by_number("D251-1", date(2024, 6, 1)) == []
    missing = repo.declared_but_missing("D251-1", date(2024, 6, 1))
    assert missing == [("LEGIARTI000049133395", "Code de l'énergie")]


def test_lexical_search_respects_date(conn: psycopg.Connection[Any]) -> None:
    repo = CorpusRepository(conn)
    hits = repo.lexical_search("catastrophes naturelles assurance", date(2026, 10, 24), 5)
    assert hits and hits[0].version.official_id == "LEGIARTI000054141744"  # L125-2 C. assur., en vigueur
    hits_2000 = repo.lexical_search("catastrophes naturelles assurance", date(2000, 1, 1), 5)
    assert "LEGIARTI000006792615" in [h.version.official_id for h in hits_2000]  # version 1985-2003


def _as_tenant(conn: psycopg.Connection[Any], tenant: uuid.UUID | None) -> None:
    conn.execute("SET ROLE avx_app")
    conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(tenant) if tenant else "",))


def test_row_level_security_isolates_tenants(ingested_url: str) -> None:
    with psycopg.connect(ingested_url, autocommit=True) as admin:
        org_a, org_b, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        admin.execute("INSERT INTO organization (id, name) VALUES (%s, 'Cabinet A'), (%s, 'Cabinet B')", (org_a, org_b))
        admin.execute(
            "INSERT INTO app_user (id, oidc_issuer, oidc_subject, email) VALUES (%s, 'https://idp.test', 'u1', 'u1@test.invalid')",
            (user,),
        )
        admin.execute(
            "INSERT INTO membership (organization_id, user_id, role) VALUES (%s, %s, 'LAWYER'), (%s, %s, 'LAWYER')",
            (org_a, user, org_b, user),
        )
        admin.execute(
            "INSERT INTO matter (organization_id, reference, title, created_by) VALUES (%s, 'A-1', 'Dossier A', %s), (%s, 'B-1', 'Dossier B', %s)",
            (org_a, user, org_b, user),
        )

    with psycopg.connect(ingested_url, autocommit=True) as app:
        _as_tenant(app, org_a)
        assert app.execute("SELECT reference FROM matter").fetchall() == [("A-1",)]
        assert app.execute("SELECT count(*) FROM organization").fetchone() == (1,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute(
                "INSERT INTO matter (organization_id, reference, title, created_by) VALUES (%s, 'X', 'intrusion', %s)",
                (org_b, user),
            )
        _as_tenant(app, None)
        assert app.execute("SELECT count(*) FROM matter").fetchone() == (0,)
        # Le corpus public reste lisible ; il n'est pas modifiable par le rôle applicatif.
        assert app.execute("SELECT count(*) FROM provision_version").fetchone()[0] >= 40  # type: ignore[index]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("UPDATE provision_version SET withdrawn_from_source = true")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("DELETE FROM access_log")

        # Résolution du principal (avant tenant) par la fonction SECURITY DEFINER dédiée.
        rows = app.execute("SELECT role FROM avx_resolve_principal('https://idp.test', 'u1')").fetchall()
        assert sorted(rows) == [("LAWYER",), ("LAWYER",)]
        assert app.execute("SELECT * FROM avx_resolve_principal('https://idp.test', 'inconnu')").fetchall() == []


def _deliver(
    tmp_path: Path, legi_fixtures: Path, official_id: str, new_branch: str | None, withdrawn: list[str]
) -> Path:
    """Construit une livraison simulée : l'article éventuellement relivré sous une
    autre branche, et une liste de suppression (chemins sans extension)."""
    source = next(legi_fixtures.rglob(f"{official_id}.xml"))
    relative = source.relative_to(legi_fixtures).as_posix()
    if new_branch is not None:
        moved = tmp_path / relative.replace("code_et_TNC_en_vigueur/code_en_vigueur", new_branch)
        moved.parent.mkdir(parents=True)
        moved.write_bytes(source.read_bytes())
    (tmp_path / "liste_suppression_legi.dat").write_text("\n".join(withdrawn) + "\n", "utf-8")
    return tmp_path


def test_branch_move_is_not_a_withdrawal(conn: psycopg.Connection[Any], legi_fixtures: Path, tmp_path: Path) -> None:
    official_id = "LEGIARTI000006792617"  # L125-2 C. assur., version 2004-2023
    old_path = conn.execute(
        "SELECT source_path FROM provision_version WHERE official_id = %s AND sys_to IS NULL", (official_id,)
    ).fetchone()[0]  # type: ignore[index]
    delivery = _deliver(
        tmp_path,
        legi_fixtures,
        official_id,
        "code_et_TNC_non_vigueur/code_non_vigueur",
        [old_path.removesuffix(".xml")],
    )
    _, stats = ingest_legi(conn, delivery)
    assert (stats.superseded, stats.withdrawals_recorded, stats.withdrawals_matched) == (1, 1, 0)
    current = conn.execute(
        "SELECT source_path, withdrawn_from_source FROM provision_version WHERE official_id = %s AND sys_to IS NULL",
        (official_id,),
    ).fetchone()
    assert current is not None and "code_non_vigueur" in current[0] and current[1] is False
    _, stats = ingest_legi(conn, legi_fixtures)  # restauration
    assert stats.superseded == 1


def test_withdrawal_matching_path_hides_version(ingested_url: str, legi_fixtures: Path, tmp_path: Path) -> None:
    official_id = "LEGIARTI000006792616"  # L125-2 C. assur., version 2003-2004
    with psycopg.connect(ingested_url, autocommit=True) as conn:
        path = conn.execute(
            "SELECT source_path FROM provision_version WHERE official_id = %s AND sys_to IS NULL", (official_id,)
        ).fetchone()[0]  # type: ignore[index]
        _, stats = ingest_legi(conn, _deliver(tmp_path, legi_fixtures, official_id, None, [path.removesuffix(".xml")]))
        assert stats.withdrawals_matched == 1
        assert CorpusRepository(conn).get_current_version(official_id) is None
        recorded = conn.execute(
            "SELECT matched FROM source_withdrawal WHERE official_id = %s ORDER BY recorded_at DESC LIMIT 1",
            (official_id,),
        ).fetchone()
        assert recorded == (True,)
        # Relivraison ultérieure du même fichier : la version redevient visible, l'historique est conservé.
        _, stats = ingest_legi(conn, legi_fixtures)
        assert stats.superseded == 1
        assert CorpusRepository(conn).get_current_version(official_id) is not None
        assert conn.execute(
            "SELECT count(*) FROM provision_version WHERE official_id = %s AND withdrawn_from_source", (official_id,)
        ).fetchone() == (1,)
