"""Plan d'un texte à une date, reconstitué à partir des nœuds de structure LEGI."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

from avocat_expert.domain.temporal import InForce, LegalPeriod


@dataclass
class TocNode:
    """Élément du plan : section ou article.

    ``in_force`` vaut ``INDETERMINE`` pour un élément dont une date n'est pas
    fixée par la source au-delà de la date de connaissance ; ``missing`` signale
    une section référencée dont le fichier n'est pas dans le corpus, ou un
    article dont aucune version courante n'est ingérée (lacune de couverture).
    """

    kind: Literal["SECTION", "ARTICLE"]
    official_id: str
    label: str
    status: str
    in_force: InForce
    missing: bool = False
    children: list[TocNode] = field(default_factory=list)

    def walk(self, depth: int = 0) -> list[tuple[int, TocNode]]:
        rows = [(depth, self)]
        for child in self.children:
            rows.extend(child.walk(depth + 1))
        return rows


@dataclass
class TableOfContents:
    document_official_id: str
    text_version_id: str
    at: date
    knowledge_date: date | None
    children: list[TocNode]
    notes: list[str]

    def walk(self) -> list[tuple[int, TocNode]]:
        return [row for child in self.children for row in child.walk()]


class StructureRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def _fetch(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def table_of_contents(
        self, document_official_id: str, at: date, knowledge_date: date | None
    ) -> TableOfContents | None:
        """Plan du texte ``document_official_id`` (cid) en vigueur à la date ``at``.

        Les entrées retenues sont celles en vigueur ou d'applicabilité
        indéterminée à la date ; les autres sont omises.
        """
        nodes = self._fetch(
            """SELECT n.id, n.kind, n.official_id, n.title
               FROM structure_node_version n JOIN legal_document d ON d.id = n.document_id
               WHERE d.official_id = %s AND n.sys_to IS NULL AND NOT n.withdrawn_from_source""",
            (document_official_id,),
        )
        if not nodes:
            return None
        notes: list[str] = []
        roots = [n for n in nodes if n["kind"] == "TEXTE"]
        root = self._choose_root(roots, at, notes)
        if root is None:
            return None
        sections = {n["official_id"]: n for n in nodes if n["kind"] == "SECTION"}
        entries: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for row in self._fetch(
            """SELECT node_version_id, entry_kind, target_official_id, number, label, source_status,
                      valid_from, valid_to, end_undetermined, dates_unknown
               FROM structure_entry WHERE node_version_id = ANY(%s) ORDER BY node_version_id, position""",
            ([n["id"] for n in nodes],),
        ):
            entries.setdefault(row["node_version_id"], []).append(row)
        article_ids = {
            e["target_official_id"] for rows in entries.values() for e in rows if e["entry_kind"] == "ARTICLE"
        }
        known_articles = {
            r["official_id"]
            for r in self._fetch(
                "SELECT official_id FROM provision_version WHERE official_id = ANY(%s) AND sys_to IS NULL",
                (list(article_ids),),
            )
        }

        def build(node_id: uuid.UUID, seen: frozenset[str]) -> list[TocNode]:
            children: list[TocNode] = []
            for e in entries.get(node_id, []):
                if e["entry_kind"] == "VERSION_TEXTE":
                    continue
                period = LegalPeriod(
                    valid_from=e["valid_from"],
                    valid_to=e["valid_to"],
                    end_undetermined=e["end_undetermined"],
                    dates_unknown=e["dates_unknown"],
                )
                state = period.in_force_at(at, knowledge_date)
                if state is InForce.NON:
                    continue
                target = e["target_official_id"]
                if e["entry_kind"] == "ARTICLE":
                    children.append(
                        TocNode(
                            kind="ARTICLE",
                            official_id=target,
                            label=e["number"] or target,
                            status=e["source_status"],
                            in_force=state,
                            missing=target not in known_articles,
                        )
                    )
                    continue
                section = sections.get(target)
                if target in seen:
                    notes.append(f"cycle de structure ignoré : {target}")
                    continue
                children.append(
                    TocNode(
                        kind="SECTION",
                        official_id=target,
                        label=(section["title"] if section else None) or e["label"] or target,
                        status=e["source_status"],
                        in_force=state,
                        missing=section is None,
                        children=build(section["id"], seen | {target}) if section else [],
                    )
                )
            return children

        return TableOfContents(
            document_official_id=document_official_id,
            text_version_id=root["official_id"],
            at=at,
            knowledge_date=knowledge_date,
            children=build(root["id"], frozenset()),
            notes=notes,
        )

    def _choose_root(self, roots: list[dict[str, Any]], at: date, notes: list[str]) -> dict[str, Any] | None:
        if len(roots) <= 1:
            return roots[0] if roots else None
        # Plusieurs versions du texte (texte non codifié) : version en vigueur à la date.
        in_force = {
            r["official_id"]
            for r in self._fetch(
                """SELECT official_id FROM document_version
                   WHERE official_id = ANY(%s) AND sys_to IS NULL AND valid_period @> %s::date""",
                ([r["official_id"] for r in roots], at),
            )
        }
        matching = [r for r in roots if r["official_id"] in in_force]
        if len(matching) == 1:
            return matching[0]
        notes.append(f"version du texte au {at} indéterminée parmi {sorted(r['official_id'] for r in roots)}")
        return None
