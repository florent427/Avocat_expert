"""Ingestion d'une archive LEGI dans le corpus, sans jamais écraser l'historique.

Règles :
* version inconnue                      -> insertion ;
* version connue, contenu et période    -> aucune écriture (idempotence) ;
  identiques
* version connue, différence            -> la ligne courante est close
  (sys_to, superseded_by) et une nouvelle ligne est insérée : la connaissance
  antérieure reste consultable ;
* retrait signalé par la source         -> enregistré ; la version courante est
  marquée ``withdrawn_from_source`` seulement si son chemin source est
  exactement celui de l'entrée de retrait (aucune suppression).

Selon la documentation XML Légifrance de la DILA (v1.2.2, 2018), une entrée de
``liste_suppression_legi.dat`` peut traduire un passage de la branche
« vigueur » à la branche « non vigueur » (fichier supprimé puis recréé
ailleurs). Le chemin source fait donc partie de la connaissance enregistrée :
un article relivré sous un autre chemin produit une nouvelle ligne, et le
retrait de l'ancien chemin ne le masque pas.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from avocat_expert.connectors.legi import CONNECTOR_VERSION, SOURCE_CODE
from avocat_expert.connectors.legi.archive import iter_article_files, read_withdrawals
from avocat_expert.connectors.legi.parser import LegiArticle, LegiFormatError, parse_article

SOURCE_DEFINITION = {
    "code": SOURCE_CODE,
    "name": "LEGI — codes, lois et règlements consolidés",
    "publisher": "Direction de l'information légale et administrative (DILA)",
    "access_method": "BULK_DUMP",
    "base_url": "https://echanges.dila.gouv.fr/OPENDATA/LEGI/",
    "licence_name": "Licence Ouverte v2.0 (Etalab)",
    "licence_url": "https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
    "licence_notes": (
        "Fiche DILA LEGI (24/08/2017) : mention obligatoire de la paternité (DILA), de l'URL de "
        "téléchargement, du nom et de la date du fichier. La métadonnée data.gouv.fr indique fr-lo "
        "(v1) : divergence à lever. Validation juridique requise avant production."
    ),
}


@dataclass
class IngestionStats:
    files_seen: int = 0
    inserted: int = 0
    unchanged: int = 0
    superseded: int = 0
    rejected: int = 0
    withdrawals_recorded: int = 0
    withdrawals_matched: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "errors"} | {"errors": self.errors[:50]}


def _returned_id(row: tuple[Any, ...] | None) -> uuid.UUID:
    if row is None:
        raise RuntimeError("RETURNING n'a renvoyé aucune ligne")
    value = row[0]
    if not isinstance(value, uuid.UUID):
        raise TypeError("identifiant inattendu")
    return value


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_source(conn: psycopg.Connection[Any]) -> uuid.UUID:
    row = conn.execute(
        """INSERT INTO legal_source (code, name, publisher, access_method, base_url,
                                     licence_name, licence_url, licence_notes)
           VALUES (%(code)s, %(name)s, %(publisher)s, %(access_method)s, %(base_url)s,
                   %(licence_name)s, %(licence_url)s, %(licence_notes)s)
           ON CONFLICT (code) DO UPDATE SET code = EXCLUDED.code
           RETURNING id""",
        SOURCE_DEFINITION,
    ).fetchone()
    return _returned_id(row)


def _ensure_document(conn: psycopg.Connection[Any], source_id: uuid.UUID, a: LegiArticle) -> uuid.UUID:
    row = conn.execute(
        """INSERT INTO legal_document (source_id, official_id, nature, title, short_title)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (official_id) DO UPDATE SET official_id = EXCLUDED.official_id
           RETURNING id""",
        (source_id, a.text_official_id, a.text_nature, a.text_title, a.text_short_title),
    ).fetchone()
    return _returned_id(row)


def _ensure_provision(conn: psycopg.Connection[Any], document_id: uuid.UUID, number: str) -> uuid.UUID:
    row = conn.execute(
        """INSERT INTO provision (document_id, kind, number) VALUES (%s, 'ARTICLE', %s)
           ON CONFLICT (document_id, kind, number) DO UPDATE SET number = EXCLUDED.number
           RETURNING id""",
        (document_id, number),
    ).fetchone()
    return _returned_id(row)


def _same_knowledge(current: tuple[Any, ...], a: LegiArticle) -> bool:
    text_sha, status, valid_from, valid_to, source_sha, source_path, withdrawn = current
    return bool(
        not withdrawn  # une relivraison après retrait constitue une connaissance nouvelle
        and source_path == a.source_path
        and text_sha == a.content_sha256
        and status == a.status
        and valid_from == a.period.valid_from
        and valid_to == a.period.valid_to
        and source_sha == a.source_file_sha256
    )


def _store_article(conn: psycopg.Connection[Any], run_id: uuid.UUID, source_id: uuid.UUID, a: LegiArticle) -> str:
    document_id = _ensure_document(conn, source_id, a)
    provision_id = _ensure_provision(conn, document_id, a.number)
    current = conn.execute(
        """SELECT id, text_sha256, source_status, valid_from, valid_to, source_file_sha256, source_path,
                  withdrawn_from_source
           FROM provision_version WHERE official_id = %s AND sys_to IS NULL FOR UPDATE""",
        (a.official_id,),
    ).fetchone()
    if current is not None and _same_knowledge(current[1:], a):
        return "unchanged"

    new_id = uuid.uuid4()
    outcome = "inserted"
    if current is not None:
        conn.execute(
            "UPDATE provision_version SET sys_to = clock_timestamp(), superseded_by = %s WHERE id = %s",
            (new_id, current[0]),
        )
        outcome = "superseded"
    conn.execute(
        """INSERT INTO provision_version (
             id, provision_id, official_id, source_status, valid_from, valid_to,
             raw_valid_from, raw_valid_to, section_path, text_content, text_sha256, nota,
             source_path, source_file_sha256, ingestion_run_id)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            new_id,
            provision_id,
            a.official_id,
            a.status,
            a.period.valid_from,
            a.period.valid_to,
            a.raw_valid_from,
            a.raw_valid_to,
            list(a.section_path),
            a.content,
            a.content_sha256,
            a.nota,
            a.source_path,
            a.source_file_sha256,
            run_id,
        ),
    )
    for declared in a.declared_versions:
        conn.execute(
            """INSERT INTO provision_version_declared
                 (provision_id, official_id, source_status, raw_valid_from, raw_valid_to, first_seen_run)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (
                provision_id,
                declared.official_id,
                declared.status,
                declared.raw_valid_from,
                declared.raw_valid_to,
                run_id,
            ),
        )
    for link in a.links:
        conn.execute(
            """INSERT INTO legal_reference (from_version_id, link_type, direction, target_official_id,
                                            target_text_id, target_label, target_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (
                new_id,
                link.link_type,
                link.direction,
                link.target_official_id,
                link.target_text_id,
                link.target_label,
                link.target_date,
            ),
        )
    return outcome


def ingest_legi(conn: psycopg.Connection[Any], location: Path) -> tuple[uuid.UUID, IngestionStats]:
    """Ingère une archive ``.tar.gz`` LEGI ou un répertoire extrait."""
    stats = IngestionStats()
    with conn.transaction():
        source_id = _ensure_source(conn)
        run_row = conn.execute(
            """INSERT INTO ingestion_run (source_id, connector_version, archive_name, archive_sha256)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (source_id, CONNECTOR_VERSION, location.name, _sha256_file(location)),
        ).fetchone()
    run_id = _returned_id(run_row)

    try:
        with conn.transaction():
            for entry in iter_article_files(location):
                stats.files_seen += 1
                try:
                    article = parse_article(entry.data, entry.path)
                except LegiFormatError as exc:
                    stats.rejected += 1
                    stats.errors.append(f"{entry.path}: {exc}")
                    continue
                outcome = _store_article(conn, run_id, source_id, article)
                setattr(stats, outcome, getattr(stats, outcome) + 1)

            for withdrawal in read_withdrawals(location):
                # L'entrée de retrait est un chemin sans extension (observé dans les deltas réels).
                updated = conn.execute(
                    """UPDATE provision_version SET withdrawn_from_source = true
                       WHERE official_id = %s AND sys_to IS NULL AND NOT withdrawn_from_source
                         AND source_path = %s""",
                    (withdrawal.official_id, withdrawal.raw_entry + ".xml"),
                ).rowcount
                conn.execute(
                    """INSERT INTO source_withdrawal (ingestion_run_id, official_id, raw_entry, matched)
                       VALUES (%s, %s, %s, %s)""",
                    (run_id, withdrawal.official_id, withdrawal.raw_entry, updated > 0),
                )
                stats.withdrawals_recorded += 1
                stats.withdrawals_matched += int(updated > 0)
    except Exception as exc:
        with conn.transaction():
            conn.execute(
                "UPDATE ingestion_run SET status = 'FAILED', finished_at = now(), error = %s, stats = %s WHERE id = %s",
                (repr(exc)[:2000], Jsonb(stats.as_dict()), run_id),
            )
        raise

    with conn.transaction():
        conn.execute("REFRESH MATERIALIZED VIEW corpus_lexeme_stats")
        conn.execute("REFRESH MATERIALIZED VIEW corpus_stats")
        conn.execute(
            "UPDATE ingestion_run SET status = 'SUCCEEDED', finished_at = now(), stats = %s WHERE id = %s",
            (Jsonb(stats.as_dict()), run_id),
        )
    return run_id, stats
