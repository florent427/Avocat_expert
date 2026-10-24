"""Exercice de sauvegarde et de restauration sur une base réelle.

Sauvegarde logique (pg_dump, format personnalisé) de la base de test ingérée,
restauration dans une base neuve, puis vérification : mêmes lignes, même
empreinte du corpus, historique toujours immuable, isolation RLS active.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql

pytestmark = pytest.mark.db

TABLES = [
    "legal_source",
    "ingestion_run",
    "legal_document",
    "provision",
    "provision_version",
    "provision_version_declared",
    "legal_reference",
    "source_withdrawal",
    "schema_migration",
]
FINGERPRINT = """SELECT md5(string_agg(official_id || ':' || text_sha256 || ':' || sys_from::text || ':'
                 || coalesce(sys_to::text, '-'), ',' ORDER BY official_id, sys_from)) FROM provision_version"""


def _snapshot(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    counts = {t: conn.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))).fetchone() for t in TABLES}
    row = conn.execute(FINGERPRINT).fetchone()
    policies = conn.execute("SELECT count(*) FROM pg_policies WHERE schemaname = 'public'").fetchone()
    return {"counts": counts, "fingerprint": row, "policies": policies}


def test_dump_and_restore_preserves_everything(ingested_url: str, admin_url: str, tmp_path: Path) -> None:
    pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    assert pg_dump and pg_restore, "pg_dump et pg_restore (client PostgreSQL 16) sont requis"
    dump = tmp_path / "avx.dump"
    subprocess.run([pg_dump, "--format=custom", "--no-owner", f"--file={dump}", ingested_url], check=True)

    target = f"avx_restore_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    target_url = psycopg.conninfo.make_conninfo(ingested_url, dbname=target)
    try:
        subprocess.run([pg_restore, "--exit-on-error", "--no-owner", f"--dbname={target_url}", str(dump)], check=True)
        with psycopg.connect(ingested_url, autocommit=True) as src, psycopg.connect(target_url, autocommit=True) as dst:
            before, after = _snapshot(src), _snapshot(dst)
            assert after == before
            assert after["counts"]["provision_version"][0] >= 40
            # Les garde-fous survivent à la restauration.
            with pytest.raises(psycopg.errors.RaiseException, match="suppression interdite"):
                dst.execute("DELETE FROM provision_version")
            assert dst.execute("SELECT relforcerowsecurity FROM pg_class WHERE relname = 'matter'").fetchone() == (
                True,
            )
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(target)))
