"""Alimentation de l'index OpenSearch depuis le corpus PostgreSQL.

* ``rebuild`` : nouvel index physique (``{alias}-{version}-{horodatage}``),
  chargé en lots depuis un curseur serveur, puis bascule atomique de l'alias
  et suppression de l'ancien index : aucune interruption de la recherche.
* ``update`` : depuis le point de contrôle, réindexe les éléments dont une
  version a été créée ou close, ou qui ont fait l'objet d'un retrait ; un
  élément sans version courante est supprimé de l'index.

Le point de contrôle est pris **avant** la lecture : un élément modifié
pendant la synchronisation sera repris à la suivante (au pire réindexé deux
fois, jamais oublié).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg

from avocat_expert.search.opensearch import INDEX_VERSION, OpenSearchClient, index_body

_DOCUMENT_SQL = """
SELECT pv.official_id, pv.id, d.official_id, d.title, p.number, pv.section_path, pv.text_content,
       pv.source_status, pv.valid_from, pv.valid_to, pv.end_undetermined, pv.dates_unknown
FROM provision_version pv
JOIN provision p ON p.id = pv.provision_id
JOIN legal_document d ON d.id = p.document_id
WHERE pv.sys_to IS NULL AND NOT pv.withdrawn_from_source"""


@dataclass
class IndexReport:
    alias: str
    physical_index: str
    indexed: int = 0
    deleted: int = 0

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _document(row: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    official_id, row_id, doc_id, title, number, section_path, text, status, start, end, undetermined, unknown = row
    return official_id, {
        "official_id": official_id,
        "version_row_id": str(row_id),
        "document_official_id": doc_id,
        "document_title": title,
        "provision_number": number,
        "section_path": " / ".join(section_path or []),
        "text": text,
        "source_status": status,
        "valid_from": start.isoformat() if start else None,
        "valid_to": end.isoformat() if end else None,
        "end_undetermined": undetermined,
        "dates_unknown": unknown,
    }


def _stream(conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...], size: int) -> Iterator[list[Any]]:
    with conn.transaction(), conn.cursor(name=f"avx_index_{uuid.uuid4().hex[:8]}") as cur:
        cur.itersize = size
        cur.execute(sql, params)
        while rows := cur.fetchmany(size):
            yield rows


def _now(conn: psycopg.Connection[Any]) -> datetime:
    row = conn.execute("SELECT clock_timestamp()").fetchone()
    return row[0] if row else datetime.now(UTC)


def rebuild(conn: psycopg.Connection[Any], client: OpenSearchClient, alias: str, batch: int = 1000) -> IndexReport:
    checkpoint = _now(conn)
    physical = f"{alias}-{INDEX_VERSION}-{checkpoint:%Y%m%d%H%M%S}"
    # Chargement initial sans rafraîchissement périodique (recommandation de chargement en masse).
    body = index_body()
    body["settings"]["index"]["refresh_interval"] = "-1"
    client.request("PUT", f"/{physical}", body)
    report = IndexReport(alias, physical)
    try:
        for rows in _stream(conn, _DOCUMENT_SQL, (), batch):
            actions: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
            for row in rows:
                official_id, source = _document(row)
                actions.append(({"index": {"_index": physical, "_id": official_id}}, source))
            report.indexed += client.bulk(actions)
        client.request("PUT", f"/{physical}/_settings", {"index": {"refresh_interval": "1s"}})
        client.request("POST", f"/{physical}/_refresh")
    except Exception:
        client.request("DELETE", f"/{physical}", ok_missing=True)
        raise
    previous = client.request("GET", f"/_alias/{alias}", ok_missing=True) or {}
    actions_alias: list[dict[str, Any]] = [{"add": {"index": physical, "alias": alias}}]
    actions_alias += [{"remove_index": {"index": old}} for old in previous if old != physical]
    client.request("POST", "/_aliases", {"actions": actions_alias})
    _save_state(conn, report, checkpoint)
    return report


def update(conn: psycopg.Connection[Any], client: OpenSearchClient, alias: str, batch: int = 1000) -> IndexReport:
    row = conn.execute(
        "SELECT physical_index, checkpoint FROM search_index_state WHERE alias = %s", (alias,)
    ).fetchone()
    if row is None:
        return rebuild(conn, client, alias, batch)
    physical, since = row
    checkpoint = _now(conn)
    changed = [
        r[0]
        for r in conn.execute(
            """SELECT official_id FROM provision_version WHERE sys_from > %(t)s OR sys_to > %(t)s
               UNION SELECT official_id FROM source_withdrawal WHERE recorded_at > %(t)s""",
            {"t": since},
        ).fetchall()
    ]
    report = IndexReport(alias, physical)
    for start in range(0, len(changed), batch):
        ids = changed[start : start + batch]
        current = {r[0]: r for r in conn.execute(_DOCUMENT_SQL + " AND pv.official_id = ANY(%s)", (ids,)).fetchall()}
        actions: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
        for official_id in ids:
            if official_id in current:
                _, source = _document(current[official_id])
                actions.append(({"index": {"_index": alias, "_id": official_id}}, source))
                report.indexed += 1
            else:
                actions.append(({"delete": {"_index": alias, "_id": official_id}}, None))
                report.deleted += 1
        client.bulk(actions, tolerate_missing_deletes=True)
    client.request("POST", f"/{alias}/_refresh")
    _save_state(conn, report, checkpoint, documents_delta=report.indexed - report.deleted)
    return report


def _save_state(
    conn: psycopg.Connection[Any], report: IndexReport, checkpoint: datetime, documents_delta: int | None = None
) -> None:
    with conn.transaction():
        if documents_delta is None:
            conn.execute(
                """INSERT INTO search_index_state (alias, physical_index, checkpoint, documents)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (alias) DO UPDATE SET physical_index = EXCLUDED.physical_index,
                     checkpoint = EXCLUDED.checkpoint, documents = EXCLUDED.documents, updated_at = now()""",
                (report.alias, report.physical_index, checkpoint, report.indexed),
            )
        else:
            conn.execute(
                """UPDATE search_index_state SET checkpoint = %s, documents = documents + %s, updated_at = now()
                   WHERE alias = %s""",
                (checkpoint, documents_delta, report.alias),
            )
