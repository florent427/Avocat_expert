"""Canal lexical OpenSearch sur un nœud réel et la base de test ingérée."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
import pytest

from avocat_expert.connectors.legi.ingest import ingest_legi
from avocat_expert.search import indexer
from avocat_expert.search.opensearch import OpenSearchClient, OpenSearchError, OpenSearchLexicalSearcher
from avocat_expert.storage.corpus import CorpusRepository

pytestmark = [pytest.mark.db, pytest.mark.search]


@pytest.fixture
def alias(opensearch_url: str) -> Iterator[str]:
    name = f"avx-test-{uuid.uuid4().hex[:8]}"
    yield name
    client = OpenSearchClient(opensearch_url)
    for physical in client.request("GET", f"/_alias/{name}", ok_missing=True) or {}:
        client.request("DELETE", f"/{physical}", ok_missing=True)


def _searcher(conn: psycopg.Connection[Any], opensearch_url: str, alias: str) -> OpenSearchLexicalSearcher:
    return OpenSearchLexicalSearcher(OpenSearchClient(opensearch_url), alias, CorpusRepository(conn))


def test_rebuild_indexes_current_corpus(conn: psycopg.Connection[Any], opensearch_url: str, alias: str) -> None:
    report = indexer.rebuild(conn, OpenSearchClient(opensearch_url), alias, batch=10)
    current = conn.execute(
        "SELECT count(*) FROM provision_version WHERE sys_to IS NULL AND NOT withdrawn_from_source"
    ).fetchone()
    assert current is not None and report.indexed == current[0]
    count = OpenSearchClient(opensearch_url).request("GET", f"/{alias}/_count")
    assert count["count"] == report.indexed


def test_search_follows_dates_and_returns_database_versions(
    conn: psycopg.Connection[Any], opensearch_url: str, alias: str
) -> None:
    indexer.rebuild(conn, OpenSearchClient(opensearch_url), alias)
    searcher = _searcher(conn, opensearch_url, alias)
    today = searcher.search("allocation d'assurance travailleurs privés d'emploi", date(2026, 10, 24), 5)
    assert "LEGIARTI000048590547" in [h.version.official_id for h in today]  # L5422-1 en vigueur
    assert all(h.version.text_content for h in today)  # texte relu dans PostgreSQL
    in_2010 = [h.version.official_id for h in searcher.search("allocation d'assurance", date(2010, 1, 1), 10)]
    assert "LEGIARTI000019071164" in in_2010 and "LEGIARTI000048590547" not in in_2010
    # Accents repliés : « prives » trouve « privés ».
    assert searcher.search("travailleurs prives", date(2026, 10, 24), 5)


def test_named_document_restriction_is_applied_by_the_engine(
    conn: psycopg.Connection[Any], opensearch_url: str, alias: str
) -> None:
    indexer.rebuild(conn, OpenSearchClient(opensearch_url), alias)
    hits = _searcher(conn, opensearch_url, alias).search(
        "assurance", date(2026, 10, 24), 20, frozenset({"LEGITEXT000006073984"})
    )
    assert hits and {h.version.document_official_id for h in hits} == {"LEGITEXT000006073984"}


def test_versions_without_fixed_start_are_never_found(
    conn: psycopg.Connection[Any], opensearch_url: str, alias: str
) -> None:
    indexer.rebuild(conn, OpenSearchClient(opensearch_url), alias)
    searcher = _searcher(conn, opensearch_url, alias)
    for year in (1990, 2026, 2300):
        found = [h.version.official_id for h in searcher.search("santé publique", date(year, 1, 1), 50)]
        assert "LEGIARTI000025453562" not in found  # début 2222-02-22 : non fixé


def test_incremental_update_follows_new_knowledge(
    conn: psycopg.Connection[Any], legi_fixtures: Path, opensearch_url: str, alias: str, tmp_path: Path
) -> None:
    client = OpenSearchClient(opensearch_url)
    indexer.rebuild(conn, client, alias)
    assert indexer.update(conn, client, alias).indexed == 0  # rien n'a changé
    official_id = "LEGIARTI000051831141"  # D251-1 C. énergie, version en vigueur (non examinée ailleurs)
    source = next(legi_fixtures.rglob(f"{official_id}.xml"))
    copy = tmp_path / "legi" / source.relative_to(legi_fixtures / "legi")
    copy.parent.mkdir(parents=True)
    copy.write_text(
        source.read_text("utf-8").replace("<DATE_FIN>2999-01-01</DATE_FIN>", "<DATE_FIN>2026-01-01</DATE_FIN>"),
        "utf-8",
    )
    ingest_legi(conn, tmp_path, enforce_order=False)
    report = indexer.update(conn, client, alias)
    assert (report.indexed, report.deleted) == (1, 0)
    doc = client.request("GET", f"/{alias}/_doc/{official_id}")
    assert doc["_source"]["valid_to"] == "2026-01-01"
    _, stats = ingest_legi(conn, legi_fixtures)  # restauration
    assert stats.superseded == 1
    assert indexer.update(conn, client, alias).indexed == 1


def test_stale_index_entries_are_ignored(conn: psycopg.Connection[Any], opensearch_url: str, alias: str) -> None:
    client = OpenSearchClient(opensearch_url)
    indexer.rebuild(conn, client, alias)
    client.request(
        "PUT",
        f"/{alias}/_doc/LEGIARTI000099999999?refresh=true",
        {"official_id": "LEGIARTI000099999999", "text": "allocation d'assurance fantôme", "valid_from": "2000-01-01"},
    )
    found = [
        h.version.official_id for h in _searcher(conn, opensearch_url, alias).search("fantôme", date(2026, 1, 1), 5)
    ]
    assert found == []  # absent de la base : jamais restitué


def test_bulk_errors_are_raised(opensearch_url: str, alias: str) -> None:
    client = OpenSearchClient(opensearch_url)
    client.request(
        "PUT", f"/{alias}-strict", {"mappings": {"dynamic": "strict", "properties": {"a": {"type": "keyword"}}}}
    )
    try:
        with pytest.raises(OpenSearchError, match="échec d'indexation"):
            client.bulk([({"index": {"_index": f"{alias}-strict", "_id": "1"}}, {"inconnu": 1})])
    finally:
        client.request("DELETE", f"/{alias}-strict", ok_missing=True)


def test_invalid_url_is_refused() -> None:
    with pytest.raises(OpenSearchError, match="URL OpenSearch invalide"):
        OpenSearchClient("ftp://exemple.invalid")
