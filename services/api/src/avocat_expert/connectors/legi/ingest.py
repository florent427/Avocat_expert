"""Ingestion d'une livraison LEGI (stock ou delta) sans jamais écraser l'historique.

Règles de connaissance (articles, versions de textes, nœuds de structure) :
* élément inconnu                       -> insertion ;
* élément connu, connaissance identique -> aucune écriture (idempotence) ;
* élément connu, différence             -> la ligne courante est close
  (sys_to, superseded_by) et une nouvelle ligne est insérée ;
* retrait signalé par la source         -> enregistré ; la ligne courante est
  marquée ``withdrawn_from_source`` seulement si son chemin source est
  exactement celui de l'entrée de retrait (aucune suppression).

Selon la documentation XML Légifrance de la DILA (v1.2.2, 2018), une entrée de
``liste_suppression_legi.dat`` peut traduire un passage de la branche
« vigueur » à la branche « non vigueur » (fichier supprimé puis recréé
ailleurs) : le chemin source fait donc partie de la connaissance.

Exploitation (ING-02) :
* une seule ingestion à la fois par source (verrou consultatif PostgreSQL) ;
* lecture en flux et validation par lots : chaque lot est une transaction et
  le point de reprise (nombre de fichiers validés, dernier chemin) est
  enregistré avec lui. Une ingestion interrompue reprend après le dernier lot
  validé, si l'archive est identique (même empreinte) ;
* ordre des livraisons : la DILA impose d'appliquer les livraisons « dans
  l'ordre croissant ». Une archive antérieure à la dernière livraison
  intégrée est refusée (elle remplacerait une connaissance plus récente par
  une plus ancienne) ; une archive non horodatée n'est acceptée que si le
  contrôle est explicitement désactivé (fixtures, livraisons de test).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from avocat_expert.connectors.legi import CONNECTOR_VERSION, SOURCE_CODE
from avocat_expert.connectors.legi.archive import ArchiveEntry, ArchiveReader, Withdrawal, archive_timestamp
from avocat_expert.connectors.legi.parser import LegiArticle, LegiFormatError, LegiLink, parse_article
from avocat_expert.connectors.legi.structure import (
    LegiStructureNode,
    LegiTextVersion,
    parse_section,
    parse_text_structure,
    parse_text_version,
)

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

DEFAULT_BATCH_SIZE = 1000
OUTCOMES = ("inserted", "unchanged", "superseded", "rejected")


class IngestionOrderError(RuntimeError):
    """La livraison ne peut pas être appliquée à cet endroit de la séquence."""


class ResumeMismatchError(RuntimeError):
    """Le point de reprise enregistré ne correspond pas au contenu de l'archive."""


@dataclass
class IngestionStats:
    files_seen: int = 0
    inserted: int = 0
    unchanged: int = 0
    superseded: int = 0
    rejected: int = 0
    withdrawals_recorded: int = 0
    withdrawals_matched: int = 0
    ignored: int = 0
    eli_index: int = 0
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def count(self, kind: str, outcome: str) -> None:
        setattr(self, outcome, getattr(self, outcome) + 1)
        bucket = self.by_kind.setdefault(kind, dict.fromkeys(OUTCOMES, 0))
        bucket[outcome] += 1

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k != "errors"} | {"errors": self.errors[:50]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IngestionStats:
        known = {k: raw[k] for k in cls.__dataclass_fields__ if k in raw}
        return cls(**known)

    def copy(self) -> IngestionStats:
        return IngestionStats.from_dict(
            self.as_dict() | {"by_kind": {k: dict(v) for k, v in self.by_kind.items()}, "errors": list(self.errors)}
        )


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


def _link_rows(owner: uuid.UUID, links: Iterable[LegiLink]) -> list[tuple[Any, ...]]:
    return [
        (
            owner,
            link.link_type,
            link.direction,
            link.target_official_id,
            link.target_text_id,
            link.target_label,
            link.target_date,
        )
        for link in links
    ]


Parsed = LegiArticle | LegiTextVersion | LegiStructureNode

_ARTICLE_STATE = """SELECT official_id, id, text_sha256, source_status, valid_from, valid_to, end_undetermined,
                           dates_unknown, source_file_sha256, source_path, withdrawn_from_source
                    FROM provision_version WHERE official_id = ANY(%s) AND sys_to IS NULL FOR UPDATE"""


class _Store:
    """Écritures d'une ingestion.

    Performance (mesurée sur le stock : environ 200 fichiers/s avec une requête
    synchrone par lecture) : l'état courant des éléments d'un lot, les textes et
    les dispositions sont lus en une requête par lot (``prefetch``) ; les
    identifiants des nouvelles lignes sont générés côté client et les écritures
    envoyées en mode pipeline. Le verrou d'ingestion de la source garantit
    qu'aucune autre écriture ne s'intercale.
    """

    def __init__(self, conn: psycopg.Connection[Any], run_id: uuid.UUID, source_id: uuid.UUID) -> None:
        self.conn = conn
        self.run_id = run_id
        self.source_id = source_id
        self._documents: dict[str, uuid.UUID] = {}
        self._provisions: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self._articles: dict[str, tuple[Any, ...] | None] = {}
        self._nodes: dict[tuple[str, str], tuple[Any, ...] | None] = {}
        self._prefetched_documents: set[uuid.UUID] = set()

    def forget_caches(self) -> None:
        # Après une annulation de transaction, des identifiants mis en cache
        # peuvent désigner des lignes qui n'existent plus.
        self._documents.clear()
        self._provisions.clear()
        self._articles.clear()
        self._nodes.clear()
        self._prefetched_documents.clear()

    def prefetch(self, items: list[Parsed]) -> None:
        """Charge en une requête par catégorie l'état courant des éléments du lot."""
        self._articles.clear()
        self._nodes.clear()
        articles = [i for i in items if isinstance(i, LegiArticle)]
        versions = [i for i in items if isinstance(i, LegiTextVersion)]
        nodes = [i for i in items if isinstance(i, LegiStructureNode)]

        cids = {a.text_official_id for a in articles} | {t.document_cid for t in versions}
        cids |= {n.document_cid for n in nodes}
        missing = [c for c in cids if c not in self._documents]
        if missing:
            for doc_id, cid, title in self.conn.execute(
                "SELECT id, official_id, title FROM legal_document WHERE official_id = ANY(%s)", (missing,)
            ).fetchall():
                if title != cid:  # titre provisoire : laissé au chemin d'écriture, qui le remplace
                    self._documents[cid] = doc_id

        ids = [a.official_id for a in articles]
        if ids:
            self._articles = dict.fromkeys(ids)
            for row in self.conn.execute(_ARTICLE_STATE, (ids,)).fetchall():
                self._articles[row[0]] = row[1:]

        for table, keys in (
            ("document_version", [("", t.official_id) for t in versions]),
            ("structure_node_version", [(n.kind, n.official_id) for n in nodes]),
        ):
            if not keys:
                continue
            for key in keys:
                self._nodes[(table, key[0] + key[1])] = None
            kind_sql = "''" if table == "document_version" else "kind"
            for row in self.conn.execute(
                f"SELECT {kind_sql} || official_id, id, source_path, source_file_sha256, withdrawn_from_source "  # noqa: S608
                f"FROM {table} WHERE official_id = ANY(%s) AND sys_to IS NULL FOR UPDATE",
                ([k[1] for k in keys],),
            ).fetchall():
                if (table, row[0]) in self._nodes:
                    self._nodes[(table, row[0])] = row[1:]

        wanted = {
            (self._documents[a.text_official_id], a.number, a.unnumbered_key or "")
            for a in articles
            if a.text_official_id in self._documents
        }
        self._prefetched_documents = {w[0] for w in wanted}
        wanted = {w for w in wanted if (w[0], w[1] or f"~{w[2]}") not in self._provisions}
        if wanted:
            docs, numbers, keys = (list(column) for column in zip(*wanted, strict=True))
            for prov_id, doc_id, number, key in self.conn.execute(
                """SELECT p.id, p.document_id, p.number, coalesce(p.unnumbered_key, '')
                   FROM provision p
                   JOIN unnest(%s::uuid[], %s::text[], %s::text[]) AS w(document_id, number, k)
                     ON p.document_id = w.document_id AND p.kind = 'ARTICLE' AND p.number = w.number
                    AND coalesce(p.unnumbered_key, '') = w.k""",
                (docs, numbers, keys),
            ).fetchall():
                self._provisions[(doc_id, number or f"~{key}")] = prov_id

    def document(self, cid: str, nature: str, title: str | None) -> uuid.UUID:
        cached = self._documents.get(cid)
        if cached is not None:
            return cached
        # Titre inconnu (fichier de structure lu avant le texte) : identifiant
        # provisoire, remplacé dès qu'un fichier porteur du titre est lu.
        row = self.conn.execute(
            """INSERT INTO legal_document (source_id, official_id, nature, title, short_title)
               VALUES (%s, %s, %s, %s, NULL)
               ON CONFLICT (official_id) DO UPDATE SET title = CASE
                 WHEN legal_document.title = legal_document.official_id THEN EXCLUDED.title
                 ELSE legal_document.title END
               RETURNING id, title = official_id""",
            (self.source_id, cid, nature, title or cid),
        ).fetchone()
        document_id = _returned_id(row)
        if row is not None and not row[1]:
            self._documents[cid] = document_id
        return document_id

    def _provision(self, document_id: uuid.UUID, number: str, unnumbered_key: str | None) -> uuid.UUID:
        key = (document_id, number or f"~{unnumbered_key}")
        cached = self._provisions.get(key)
        if cached is not None:
            return cached
        if document_id in self._prefetched_documents:
            # Absente du préchargement : création, identifiant client, sans aller-retour.
            provision_id = uuid.uuid4()
            self.conn.execute(
                "INSERT INTO provision (id, document_id, kind, number, unnumbered_key) "
                "VALUES (%s, %s, 'ARTICLE', %s, %s)",
                (provision_id, document_id, number, unnumbered_key),
            )
        else:
            provision_id = _returned_id(
                self.conn.execute(
                    """INSERT INTO provision (document_id, kind, number, unnumbered_key) VALUES (%s, 'ARTICLE', %s, %s)
                       ON CONFLICT (document_id, kind, number, (coalesce(unnumbered_key, '')))
                       DO UPDATE SET number = EXCLUDED.number
                       RETURNING id""",
                    (document_id, number, unnumbered_key),
                ).fetchone()
            )
        self._provisions[key] = provision_id
        return provision_id

    def article(self, a: LegiArticle) -> str:
        document_id = self.document(a.text_official_id, a.text_nature, a.text_title)
        provision_id = self._provision(document_id, a.number, a.unnumbered_key)
        if a.official_id in self._articles:
            current = self._articles[a.official_id]
        else:
            row = self.conn.execute(_ARTICLE_STATE, ([a.official_id],)).fetchone()
            current = row[1:] if row else None
        if current is not None:
            text_sha, status, valid_from, valid_to, end_undetermined, unknown, source_sha, source_path, withdrawn = (
                current[1:]
            )
            if (
                not withdrawn  # une relivraison après retrait constitue une connaissance nouvelle
                and source_path == a.source_path
                and text_sha == a.content_sha256
                and status == a.status
                and valid_from == a.period.valid_from
                and valid_to == a.period.valid_to
                and end_undetermined == a.period.end_undetermined
                and unknown == a.period.dates_unknown
                and source_sha == a.source_file_sha256
            ):
                return "unchanged"

        new_id = uuid.uuid4()
        outcome = "inserted"
        if current is not None:
            self.conn.execute(
                "UPDATE provision_version SET sys_to = clock_timestamp(), superseded_by = %s WHERE id = %s",
                (new_id, current[0]),
            )
            outcome = "superseded"
        # Un même identifiant peut reparaître dans le lot (changement de branche).
        self._articles[a.official_id] = (
            new_id,
            a.content_sha256,
            a.status,
            a.period.valid_from,
            a.period.valid_to,
            a.period.end_undetermined,
            a.period.dates_unknown,
            a.source_file_sha256,
            a.source_path,
            False,
        )
        self.conn.execute(
            """INSERT INTO provision_version (
                 id, provision_id, official_id, source_status, valid_from, valid_to, end_undetermined,
                 dates_unknown, raw_valid_from, raw_valid_to, section_path, text_content, text_sha256, nota,
                 source_path, source_file_sha256, ingestion_run_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                new_id,
                provision_id,
                a.official_id,
                a.status,
                a.period.valid_from,
                a.period.valid_to,
                a.period.end_undetermined,
                a.period.dates_unknown,
                a.raw_valid_from,
                a.raw_valid_to,
                list(a.section_path),
                a.content,
                a.content_sha256,
                a.nota,
                a.source_path,
                a.source_file_sha256,
                self.run_id,
            ),
        )
        with self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO provision_version_declared
                     (provision_id, official_id, source_status, raw_valid_from, raw_valid_to, first_seen_run)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                [
                    (provision_id, d.official_id, d.status, d.raw_valid_from, d.raw_valid_to, self.run_id)
                    for d in a.declared_versions
                ],
            )
            cur.executemany(
                """INSERT INTO legal_reference (from_version_id, link_type, direction, target_official_id,
                                                target_text_id, target_label, target_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                _link_rows(new_id, a.links),
            )
        return outcome

    def _close_or_keep(
        self, table: str, key_sql: str, key: tuple[Any, ...], path: str, sha: str, new_id: uuid.UUID
    ) -> tuple[str, Any]:
        cache_key = (table, "".join(str(k) for k in key) if table != "document_version" else str(key[0]))
        if cache_key in self._nodes:
            current = self._nodes[cache_key]
        else:
            current = self.conn.execute(
                f"SELECT id, source_path, source_file_sha256, withdrawn_from_source FROM {table} "  # noqa: S608
                f"WHERE {key_sql} AND sys_to IS NULL FOR UPDATE",
                key,
            ).fetchone()
        if current is not None and current[1] == path and current[2] == sha and not current[3]:
            return "unchanged", None
        self._nodes[cache_key] = (new_id, path, sha, False)
        if current is None:
            return "inserted", None
        return "superseded", current[0]

    def text_version(self, t: LegiTextVersion) -> str:
        document_id = self.document(t.document_cid, t.nature, t.title_full or t.title)
        new_id = uuid.uuid4()
        outcome, previous = self._close_or_keep(
            "document_version", "official_id = %s", (t.official_id,), t.source_path, t.source_file_sha256, new_id
        )
        if outcome == "unchanged":
            return outcome
        if previous is not None:
            self.conn.execute(
                "UPDATE document_version SET sys_to = clock_timestamp(), superseded_by = %s WHERE id = %s",
                (new_id, previous),
            )
        self.conn.execute(
            """INSERT INTO document_version (
                 id, document_id, official_id, nature, title, title_full, source_status,
                 valid_from, valid_to, end_undetermined, dates_unknown, raw_valid_from, raw_valid_to, number, nor,
                 publication_date, raw_publication_date, signature_date, raw_signature_date, last_modified,
                 upcoming_versions, publication_origin, authority, ministry, visas, signatories,
                 preparatory_work, nota, abrogation, rectification, source_path, source_file_sha256,
                 ingestion_run_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                new_id,
                document_id,
                t.official_id,
                t.nature,
                t.title,
                t.title_full,
                t.status,
                t.period.valid_from,
                t.period.valid_to,
                t.period.end_undetermined,
                t.period.dates_unknown,
                t.raw_valid_from,
                t.raw_valid_to,
                t.number,
                t.nor,
                t.publication_date,
                t.raw_publication_date,
                t.signature_date,
                t.raw_signature_date,
                t.last_modified,
                list(t.upcoming_versions),
                t.publication_origin,
                t.authority,
                t.ministry,
                t.visas,
                t.signatories,
                t.preparatory_work,
                t.nota,
                t.abrogation,
                t.rectification,
                t.source_path,
                t.source_file_sha256,
                self.run_id,
            ),
        )
        with self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO document_reference (from_document_version_id, link_type, direction,
                                                   target_official_id, target_text_id, target_label, target_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                _link_rows(new_id, t.links),
            )
        return "superseded" if previous is not None else "inserted"

    def structure_node(self, n: LegiStructureNode) -> str:
        document_id = self.document(n.document_cid, n.document_nature, n.document_title)
        new_id = uuid.uuid4()
        outcome, previous = self._close_or_keep(
            "structure_node_version",
            "kind = %s AND official_id = %s",
            (n.kind, n.official_id),
            n.source_path,
            n.source_file_sha256,
            new_id,
        )
        if outcome == "unchanged":
            return outcome
        if previous is not None:
            self.conn.execute(
                "UPDATE structure_node_version SET sys_to = clock_timestamp(), superseded_by = %s WHERE id = %s",
                (new_id, previous),
            )
        context = [[title.model_dump() for title in level] for level in n.context]
        self.conn.execute(
            """INSERT INTO structure_node_version (id, kind, official_id, document_id, title, commentary, context,
                                                   source_path, source_file_sha256, ingestion_run_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                new_id,
                n.kind,
                n.official_id,
                document_id,
                n.title,
                n.commentary,
                Jsonb(context),
                n.source_path,
                n.source_file_sha256,
                self.run_id,
            ),
        )
        with self.conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO structure_entry (node_version_id, position, entry_kind, target_official_id, target_cid,
                                                number, label, level, source_status, valid_from, valid_to,
                                                end_undetermined, dates_unknown, raw_valid_from, raw_valid_to, origin)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        new_id,
                        e.position,
                        e.kind,
                        e.target_official_id,
                        e.target_cid,
                        e.number,
                        e.label,
                        e.level,
                        e.status,
                        e.period.valid_from,
                        e.period.valid_to,
                        e.period.end_undetermined,
                        e.period.dates_unknown,
                        e.raw_valid_from,
                        e.raw_valid_to,
                        e.origin,
                    )
                    for e in n.entries
                ],
            )
        return "superseded" if previous is not None else "inserted"

    @staticmethod
    def parse(entry: ArchiveEntry) -> Parsed:
        if entry.kind == "ARTICLE":
            return parse_article(entry.data, entry.path)
        if entry.kind == "TEXT_VERSION":
            return parse_text_version(entry.data, entry.path)
        if entry.kind == "TEXT_STRUCT":
            return parse_text_structure(entry.data, entry.path)
        return parse_section(entry.data, entry.path)

    def store(self, item: Parsed) -> str:
        if isinstance(item, LegiArticle):
            return self.article(item)
        if isinstance(item, LegiTextVersion):
            return self.text_version(item)
        return self.structure_node(item)

    def withdrawal(self, w: Withdrawal) -> bool:
        # L'entrée de retrait est un chemin sans extension (observé dans les deltas réels).
        path = w.raw_entry + ".xml"
        prefix = w.official_id[:8]
        tables = {
            "LEGIARTI": ("provision_version",),
            "LEGITEXT": ("document_version", "structure_node_version"),
            "LEGISCTA": ("structure_node_version",),
        }.get(prefix, ())
        matched = 0
        for table in tables:
            matched += self.conn.execute(
                f"UPDATE {table} SET withdrawn_from_source = true "  # noqa: S608 — noms de tables fixes
                "WHERE official_id = %s AND sys_to IS NULL AND NOT withdrawn_from_source AND source_path = %s",
                (w.official_id, path),
            ).rowcount
        self.conn.execute(
            """INSERT INTO source_withdrawal (ingestion_run_id, official_id, raw_entry, matched)
               VALUES (%s, %s, %s, %s)""",
            (self.run_id, w.official_id, w.raw_entry, matched > 0),
        )
        return matched > 0


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


def _check_order(conn: psycopg.Connection[Any], source_id: uuid.UUID, name: str, stamp: datetime | None) -> None:
    if stamp is None:
        raise IngestionOrderError(
            f"archive non horodatée ({name}) : ordre d'application invérifiable "
            "(désactiver explicitement le contrôle pour une livraison de test)"
        )
    row = conn.execute(
        "SELECT max(archive_timestamp) FROM ingestion_run WHERE source_id = %s AND status = 'SUCCEEDED'",
        (source_id,),
    ).fetchone()
    latest = row[0] if row else None
    if latest is not None and stamp < latest:
        raise IngestionOrderError(
            f"archive {name} antérieure à la dernière livraison intégrée ({latest:%Y-%m-%d %H:%M:%S}) : "
            "son application remplacerait une connaissance plus récente"
        )


def _open_run(
    conn: psycopg.Connection[Any], source_id: uuid.UUID, location: Path, sha: str | None, stamp: datetime | None
) -> tuple[uuid.UUID, IngestionStats, int, str | None]:
    """Reprend l'ingestion interrompue de la même archive par la même version du
    connecteur (une correction du connecteur impose une nouvelle lecture
    complète, idempotente), ou en ouvre une nouvelle.

    Appelée sous le verrou d'ingestion de la source : une ingestion encore
    « RUNNING » est nécessairement interrompue."""
    conn.execute(
        """UPDATE ingestion_run SET status = 'FAILED', finished_at = now(),
                                    error = coalesce(error, 'interrompue (processus arrêté)')
           WHERE source_id = %s AND status = 'RUNNING'""",
        (source_id,),
    )
    if sha is not None:
        row = conn.execute(
            """SELECT id, stats, files_committed, last_committed_path FROM ingestion_run
               WHERE source_id = %s AND archive_sha256 = %s AND status = 'FAILED' AND files_committed > 0
                 AND connector_version = %s
               ORDER BY started_at DESC LIMIT 1""",
            (source_id, sha, CONNECTOR_VERSION),
        ).fetchone()
        if row is not None:
            run_id, raw_stats, committed, last_path = row
            conn.execute(
                """UPDATE ingestion_run SET status = 'RUNNING', finished_at = NULL, error = NULL,
                                            resume_count = resume_count + 1 WHERE id = %s""",
                (run_id,),
            )
            return run_id, IngestionStats.from_dict(raw_stats or {}), int(committed), last_path
    row = conn.execute(
        """INSERT INTO ingestion_run (source_id, connector_version, archive_name, archive_sha256, archive_timestamp)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (source_id, CONNECTOR_VERSION, location.name, sha, stamp),
    ).fetchone()
    return _returned_id(row), IngestionStats(), 0, None


def _lock_key(conn: psycopg.Connection[Any]) -> int:
    row = conn.execute("SELECT hashtext(%s)", (f"avx_ingest:{SOURCE_CODE}",)).fetchone()
    return int(row[0]) if row else 0


def ingest_legi(
    conn: psycopg.Connection[Any],
    location: Path,
    *,
    enforce_order: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[uuid.UUID, IngestionStats]:
    """Ingère une archive ``.tar.gz`` LEGI (stock ou delta) ou un répertoire extrait."""
    if conn.autocommit is False:
        raise ValueError("connexion en mode autocommit requise (une transaction par lot)")
    lock = _lock_key(conn)
    conn.execute("SELECT pg_advisory_lock(%s)", (lock,))
    try:
        return _ingest_locked(conn, location, enforce_order=enforce_order, batch_size=batch_size)
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (lock,))


def _ingest_locked(
    conn: psycopg.Connection[Any], location: Path, *, enforce_order: bool, batch_size: int
) -> tuple[uuid.UUID, IngestionStats]:
    sha = _sha256_file(location)
    stamp = archive_timestamp(location.name)
    with conn.transaction():
        source_id = _ensure_source(conn)
        if enforce_order:
            _check_order(conn, source_id, location.name, stamp)
        run_id, stats, skip, expected_last = _open_run(conn, source_id, location, sha, stamp)

    store = _Store(conn, run_id, source_id)
    reader = ArchiveReader(location)
    committed = skip
    try:
        batch: list[ArchiveEntry] = []
        index = 0
        for entry in reader.entries(skip=skip):
            index += 1
            if index <= skip:
                if index == skip and entry.path != expected_last:
                    raise ResumeMismatchError(
                        f"point de reprise incohérent : fichier n° {skip} = {entry.path}, attendu {expected_last}"
                    )
                continue
            batch.append(entry)
            if len(batch) >= batch_size:
                stats = _commit_batch(store, run_id, batch, stats, committed + len(batch))
                committed += len(batch)
                batch = []
        if batch:
            stats = _commit_batch(store, run_id, batch, stats, committed + len(batch))
            committed += len(batch)
        if index < skip:
            raise ResumeMismatchError(f"archive plus courte ({index} fichiers) que le point de reprise ({skip})")

        with conn.transaction():
            # Le compteur de retraits repart de zéro : la liste est relue intégralement à chaque passage.
            stats.withdrawals_recorded = stats.withdrawals_matched = 0
            for withdrawal in reader.withdrawals:
                stats.withdrawals_recorded += 1
                stats.withdrawals_matched += int(store.withdrawal(withdrawal))
            stats.ignored = reader.ignored + reader.oversized
            stats.eli_index = reader.eli_index
            if stats.inserted or stats.superseded or stats.withdrawals_matched:
                conn.execute("REFRESH MATERIALIZED VIEW corpus_lexeme_stats")
                conn.execute("REFRESH MATERIALIZED VIEW corpus_stats")
            conn.execute(
                """UPDATE ingestion_run SET status = 'SUCCEEDED', finished_at = now(), stats = %s,
                                            files_committed = %s WHERE id = %s""",
                (Jsonb(stats.as_dict()), committed, run_id),
            )
    except Exception as exc:
        with conn.transaction():
            conn.execute(
                "UPDATE ingestion_run SET status = 'FAILED', finished_at = now(), error = %s WHERE id = %s",
                (repr(exc)[:2000], run_id),
            )
        raise
    return run_id, stats


def _commit_batch(
    store: _Store, run_id: uuid.UUID, batch: list[ArchiveEntry], stats: IngestionStats, committed: int
) -> IngestionStats:
    """Traite un lot dans une transaction ; renvoie les statistiques validées."""
    working = stats.copy()
    parsed: list[tuple[ArchiveEntry, Parsed | None]] = []
    for entry in batch:
        working.files_seen += 1
        try:
            parsed.append((entry, store.parse(entry)))
        except LegiFormatError as exc:
            working.count(entry.kind, "rejected")
            working.errors.append(f"{entry.path}: {exc}")
    try:
        with store.conn.transaction():
            store.prefetch([item for _, item in parsed if item is not None])
            with store.conn.pipeline():
                for entry, item in parsed:
                    if item is not None:
                        working.count(entry.kind, store.store(item))
            store.conn.execute(
                "UPDATE ingestion_run SET files_committed = %s, last_committed_path = %s, stats = %s WHERE id = %s",
                (committed, batch[-1].path, Jsonb(working.as_dict()), run_id),
            )
    except Exception:
        store.forget_caches()
        raise
    return working
