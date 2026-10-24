"""Exécution des migrations SQL versionnées (``services/api/migrations``).

Chaque migration est appliquée une seule fois, dans une transaction, et son
empreinte est enregistrée : une migration déjà appliquée puis modifiée est
détectée et refusée.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import psycopg

# Dans le dépôt : services/api/migrations ; dans l'image : AVX_MIGRATIONS_DIR.
MIGRATIONS_DIR = Path(os.environ.get("AVX_MIGRATIONS_DIR") or Path(__file__).resolve().parents[3] / "migrations")
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    pass


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    files = sorted(p for p in directory.iterdir() if _NAME.match(p.name))
    versions = [p.name[:4] for p in files]
    if len(set(versions)) != len(versions):
        raise MigrationError("numéros de migration dupliqués")
    return files


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migration (
             version text PRIMARY KEY,
             name text NOT NULL,
             sha256 char(64) NOT NULL,
             applied_at timestamptz NOT NULL DEFAULT now())"""
    )
    conn.commit()
    applied = {row[0]: row[1] for row in conn.execute("SELECT version, sha256 FROM schema_migration").fetchall()}
    newly_applied = []
    for path in discover(directory):
        version = path.name[:4]
        sql = path.read_text("utf-8")
        digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        if version in applied:
            if applied[version] != digest:
                raise MigrationError(f"la migration {path.name} a été modifiée après application")
            continue
        with conn.transaction():
            conn.execute(sql.encode("utf-8"))  # SQL versionné du dépôt, sans paramètre
            conn.execute(
                "INSERT INTO schema_migration (version, name, sha256) VALUES (%s, %s, %s)",
                (version, path.name, digest),
            )
        newly_applied.append(path.name)
    return newly_applied
