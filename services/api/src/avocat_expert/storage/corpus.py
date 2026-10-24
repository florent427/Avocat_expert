"""Accès au corpus juridique (lecture et écriture bitemporelle)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

from avocat_expert.contracts.common import SourceReference

_VERSION_COLUMNS = """
  pv.id, pv.official_id, pv.source_status, pv.valid_from, pv.valid_to, pv.end_undetermined, pv.dates_unknown,
  pv.text_content,
  pv.text_sha256, pv.source_path, pv.source_file_sha256, pv.section_path, pv.provision_id,
  p.number AS provision_number, d.official_id AS document_official_id, d.title AS document_title,
  d.territorial_scope, s.code AS source_code, r.connector_version, r.archive_name
"""

_VERSION_FROM = """
  FROM provision_version pv
  JOIN provision p ON p.id = pv.provision_id
  JOIN legal_document d ON d.id = p.document_id
  JOIN legal_source s ON s.id = d.source_id
  JOIN ingestion_run r ON r.id = pv.ingestion_run_id
"""


BM25_K1 = 1.2
BM25_B = 0.75


def _quote_lexeme(lexeme: str) -> str:
    return "'" + lexeme.replace("\\", "\\\\").replace("'", "''") + "'"


@dataclass(frozen=True)
class VersionRecord:
    id: uuid.UUID
    official_id: str
    source_status: str
    valid_from: date | None
    valid_to: date | None
    end_undetermined: bool
    dates_unknown: bool
    text_content: str
    provision_id: uuid.UUID
    provision_number: str
    document_official_id: str
    document_title: str
    territorial_scope: list[str] | None
    section_path: list[str]
    reference: SourceReference

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> VersionRecord:
        return cls(
            id=row["id"],
            official_id=row["official_id"],
            source_status=row["source_status"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            end_undetermined=row["end_undetermined"],
            dates_unknown=row["dates_unknown"],
            text_content=row["text_content"],
            provision_id=row["provision_id"],
            provision_number=row["provision_number"],
            document_official_id=row["document_official_id"],
            document_title=row["document_title"],
            territorial_scope=row["territorial_scope"],
            section_path=list(row["section_path"] or []),
            reference=SourceReference(
                source_code=row["source_code"],
                official_id=row["official_id"],
                document_official_id=row["document_official_id"],
                document_title=row["document_title"],
                provision_number=row["provision_number"],
                valid_from=row["valid_from"],
                valid_to=row["valid_to"],
                end_undetermined=row["end_undetermined"],
                dates_unknown=row["dates_unknown"],
                source_status=row["source_status"],
                source_path=row["source_path"],
                source_file_sha256=row["source_file_sha256"],
                source_archive=row["archive_name"],
                connector_version=row["connector_version"],
            ),
        )


@dataclass(frozen=True)
class LexicalHit:
    version: VersionRecord
    score: float


# BM25 calculé en SQL ; seules des constantes du module sont interpolées.
_BM25_SQL = f"""
WITH stats AS (SELECT document_count, average_length FROM corpus_stats),
    q AS (SELECT t.lexeme, coalesce(ls.document_frequency, 0) AS df
          FROM unnest(%s::text[]) AS t(lexeme)
          LEFT JOIN corpus_lexeme_stats ls ON ls.lexeme = t.lexeme),
    cand AS (SELECT pv.id, pv.tsv, avx_tsv_length(pv.tsv) AS dl
             FROM provision_version pv
             WHERE pv.sys_to IS NULL AND NOT pv.withdrawn_from_source
               AND pv.valid_period @> %s::date
               AND pv.tsv @@ to_tsquery('avx_fr'::regconfig, %s)),
    scored AS (
      SELECT c.id,
             sum(ln(1 + (s.document_count - q.df + 0.5) / (q.df + 0.5))
                 * (tf.n * (%s + 1))
                 / (tf.n + %s * (1 - %s + %s * c.dl / nullif(s.average_length, 0)))) AS score
      FROM cand c
      CROSS JOIN stats s
      CROSS JOIN LATERAL (SELECT u.lexeme, coalesce(array_length(u.positions, 1), 1) AS n
                          FROM unnest(c.tsv) u) tf
      JOIN q ON q.lexeme = tf.lexeme
      GROUP BY c.id)
  SELECT {_VERSION_COLUMNS}, scored.score {_VERSION_FROM}
  JOIN scored ON scored.id = pv.id
  ORDER BY scored.score DESC, pv.official_id LIMIT %s"""  # noqa: S608


class CorpusRepository:
    """Lecture du corpus dans l'état de connaissance courant (``sys_to IS NULL``)."""

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def _fetch(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def get_current_version(self, official_id: str) -> VersionRecord | None:
        rows = self._fetch(
            f"SELECT {_VERSION_COLUMNS} {_VERSION_FROM} "
            "WHERE pv.official_id = %s AND pv.sys_to IS NULL AND NOT pv.withdrawn_from_source",
            (official_id,),
        )
        return VersionRecord.from_row(rows[0]) if rows else None

    def versions_of_provision(self, provision_id: uuid.UUID) -> list[VersionRecord]:
        rows = self._fetch(
            f"SELECT {_VERSION_COLUMNS} {_VERSION_FROM} "
            "WHERE pv.provision_id = %s AND pv.sys_to IS NULL AND NOT pv.withdrawn_from_source "
            "ORDER BY pv.valid_from NULLS LAST, pv.official_id",
            (provision_id,),
        )
        return [VersionRecord.from_row(r) for r in rows]

    def find_in_force_by_number(self, number: str, as_of: date) -> list[VersionRecord]:
        rows = self._fetch(
            f"SELECT {_VERSION_COLUMNS} {_VERSION_FROM} "
            "WHERE p.number = %s AND pv.sys_to IS NULL AND NOT pv.withdrawn_from_source "
            "AND pv.valid_period @> %s::date ORDER BY d.title",
            (number, as_of),
        )
        return [VersionRecord.from_row(r) for r in rows]

    def lexical_search(self, query: str, as_of: date, limit: int) -> list[LexicalHit]:
        """BM25 (k1=1,2 ; b=0,75) calculé dans PostgreSQL à partir des tsvector.

        Les fréquences de termes proviennent des positions des lexèmes (plafonnées
        à 256 par PostgreSQL), les fréquences documentaires et la longueur moyenne
        des vues ``corpus_lexeme_stats`` et ``corpus_stats``. Les candidats sont
        les versions en vigueur à la date contenant au moins un terme.
        """
        lexemes = self._fetch(
            "SELECT DISTINCT unnest(tsvector_to_array(to_tsvector('avx_fr'::regconfig, %s))) AS lexeme", (query,)
        )
        terms = sorted(r["lexeme"] for r in lexemes)
        if not terms:
            return []
        rows = self._fetch(
            _BM25_SQL,
            (terms, as_of, " | ".join(_quote_lexeme(t) for t in terms), BM25_K1, BM25_K1, BM25_B, BM25_B, limit),
        )
        return [LexicalHit(VersionRecord.from_row(r), float(r["score"])) for r in rows]

    def knowledge_date(self, source_code: str) -> date | None:
        """Date de la dernière livraison de la source intégrée avec succès."""
        rows = self._fetch("SELECT avx_knowledge_date(%s) AS d", (source_code,))
        value = rows[0]["d"] if rows else None
        return value if isinstance(value, date) else None

    def document_titles(self) -> list[tuple[str, str, str | None]]:
        """(identifiant officiel, titre, titre court) des textes du corpus."""
        rows = self._fetch("SELECT official_id, title, short_title FROM legal_document ORDER BY official_id", ())
        return [(r["official_id"], r["title"], r["short_title"]) for r in rows]

    def declared_but_missing(self, number: str, as_of: date) -> list[tuple[str, str]]:
        """Versions déclarées par la source (bloc VERSIONS), couvrant la date,
        mais absentes du corpus ingéré : signale une lacune de couverture."""
        rows = self._fetch(
            """SELECT DISTINCT dv.official_id, d.title
               FROM provision_version_declared dv
               JOIN provision p ON p.id = dv.provision_id
               JOIN legal_document d ON d.id = p.document_id
               WHERE p.number = %s
                 AND dv.raw_valid_from ~ '^\\d{4}-\\d{2}-\\d{2}$'
                 AND dv.raw_valid_from::date <= %s
                 AND (dv.raw_valid_to IS NULL OR dv.raw_valid_to !~ '^\\d{4}-\\d{2}-\\d{2}$'
                      OR dv.raw_valid_to::date > %s)
                 AND (dv.raw_valid_to IS NULL OR dv.raw_valid_to !~ '^\\d{4}-\\d{2}-\\d{2}$'
                      OR dv.raw_valid_to::date > dv.raw_valid_from::date)
                 AND NOT EXISTS (SELECT 1 FROM provision_version pv
                                 WHERE pv.official_id = dv.official_id AND pv.sys_to IS NULL)
               ORDER BY dv.official_id""",
            (number, as_of, as_of),
        )
        return [(r["official_id"], r["title"]) for r in rows]
