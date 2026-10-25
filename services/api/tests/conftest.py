"""Fixtures de test.

* Les tests ``db`` utilisent une base PostgreSQL réelle, créée pour la
  session à partir de ``AVX_TEST_DATABASE_URL`` (URL d'administration) ;
  ils sont ignorés — et signalés comme tels — si la variable est absente.
* Les tests ``engine`` utilisent le binaire Rust désigné par ``LEXVERIF_BIN``.
* Les tests ``search`` utilisent un nœud OpenSearch réel (``AVX_TEST_OPENSEARCH_URL``).
* Les tests ``embedding`` utilisent les fichiers du modèle d'embeddings
  (``AVX_TEST_EMBEDDING_MODEL_DIR``, obtenus par ``avx telecharger-modele``).
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parents[3]
LEGI_FIXTURES = REPO_ROOT / "fixtures" / "legi" / "LEGI_20261023-215041"


@pytest.fixture(scope="session")
def legi_fixtures() -> Path:
    return LEGI_FIXTURES


@pytest.fixture(scope="session")
def admin_url() -> str:
    url = os.environ.get("AVX_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AVX_TEST_DATABASE_URL non défini : tests base de données ignorés")
    return url


def _with_dbname(url: str, dbname: str) -> str:
    return psycopg.conninfo.make_conninfo(url, dbname=dbname)


@pytest.fixture(scope="session")
def database_url(admin_url: str) -> Iterator[str]:
    name = f"avx_test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = _with_dbname(admin_url, name)
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture(scope="session")
def migrated_url(database_url: str) -> str:
    from avocat_expert.storage.migrate import apply_migrations

    with psycopg.connect(database_url, autocommit=True) as conn:
        apply_migrations(conn)
    return database_url


@pytest.fixture(scope="session")
def ingested_url(migrated_url: str, legi_fixtures: Path) -> str:
    from avocat_expert.connectors.legi.ingest import ingest_legi

    with psycopg.connect(migrated_url, autocommit=True) as conn:
        _, stats = ingest_legi(conn, legi_fixtures)
    assert stats.rejected == 0, stats.errors
    return migrated_url


@pytest.fixture
def conn(ingested_url: str) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(ingested_url, autocommit=True) as connection:
        yield connection


@pytest.fixture(scope="session")
def opensearch_url() -> str:
    url = os.environ.get("AVX_TEST_OPENSEARCH_URL")
    if not url:
        pytest.skip("AVX_TEST_OPENSEARCH_URL non défini : tests OpenSearch ignorés")
    return url


@pytest.fixture(scope="session")
def embedding_model_dir() -> Path:
    directory = os.environ.get("AVX_TEST_EMBEDDING_MODEL_DIR")
    if not directory:
        pytest.skip("AVX_TEST_EMBEDDING_MODEL_DIR non défini : tests du modèle d'embeddings ignorés")
    return Path(directory)


@pytest.fixture(scope="session")
def lexverif_bin() -> str:
    candidate = os.environ.get("LEXVERIF_BIN") or str(REPO_ROOT / "engine" / "target" / "debug" / "lexverif")
    resolved = shutil.which(candidate)
    if resolved is None:
        pytest.skip("binaire lexverif introuvable (cargo build dans engine/ ou LEXVERIF_BIN)")
    return resolved
