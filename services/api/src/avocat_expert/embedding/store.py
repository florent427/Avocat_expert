"""Calcul et conservation des embeddings du corpus (migration 0013).

Texte vectorisé : intitulé du texte, chemin dans le plan, numéro, puis texte
de l'article ; le contexte situe un article court (« Les dispositions du
présent chapitre… ») que son seul texte ne permet pas de rattacher.
Au-delà de 512 jetons, la fin de l'article n'est pas vectorisée (limite du
modèle, signalée dans l'ADR 0017).

Calcul idempotent et repris là où il s'est arrêté : seules les versions
courantes sans vecteur pour le modèle sont traitées, par lots validés.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import numpy as np
import psycopg

from avocat_expert.embedding.models import ModelSpec


class PassageEmbedder(Protocol):
    spec: ModelSpec

    def embed_passages(self, texts: list[str]) -> np.ndarray[Any, np.dtype[np.float32]]: ...


def passage_text(document_title: str, section_path: Sequence[str], number: str | None, text: str) -> str:
    head = [document_title, *section_path]
    if number:
        head.append(f"Article {number}")
    return " > ".join(head) + "\n" + text


def input_sha256(spec: ModelSpec, passage: str) -> str:
    return hashlib.sha256((spec.passage_prefix + passage).encode("utf-8")).hexdigest()


def vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def register_model(conn: psycopg.Connection[Any], spec: ModelSpec) -> None:
    conn.execute(
        """INSERT INTO embedding_model (key, repository, revision, dimension) VALUES (%s, %s, %s, %s)
           ON CONFLICT (key) DO NOTHING""",
        (spec.key, spec.repository, spec.revision, spec.dimension),
    )
    row = conn.execute(
        "SELECT repository, revision, dimension FROM embedding_model WHERE key = %s", (spec.key,)
    ).fetchone()
    if row != (spec.repository, spec.revision, spec.dimension):
        raise ValueError(f"modèle {spec.key} déjà enregistré avec d'autres caractéristiques : {row}")


@dataclass
class EmbeddingReport:
    model: str
    versions: int = 0
    computed: int = 0
    reused: int = 0

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


_CANDIDATES = """
SELECT pv.id, d.title, pv.section_path, p.number, pv.text_content
FROM provision_version pv
JOIN provision p ON p.id = pv.provision_id
JOIN legal_document d ON d.id = p.document_id
WHERE pv.sys_to IS NULL AND NOT pv.withdrawn_from_source AND pv.id > %(after)s
  AND NOT EXISTS (SELECT 1 FROM provision_embedding e WHERE e.model_key = %(model)s AND e.version_id = pv.id)
  AND (%(documents)s::text[] IS NULL OR d.official_id = ANY(%(documents)s::text[]))
  AND (%(nature)s::text IS NULL OR d.nature = %(nature)s::text)
  AND (%(as_of)s::date IS NULL OR pv.valid_period @> %(as_of)s::date)
ORDER BY pv.id
LIMIT %(n)s"""


def compute_missing(
    conn: psycopg.Connection[Any],
    embedder: PassageEmbedder,
    *,
    documents: Sequence[str] | None = None,
    nature: str | None = None,
    as_of: date | None = None,
    batch: int = 256,
    limit: int | None = None,
) -> EmbeddingReport:
    """Vectorise les versions courantes du périmètre qui n'ont pas encore de
    vecteur pour ce modèle. Périmètre : textes, nature (ex. ``CODE``), versions
    en vigueur à une date ; aucun filtre : tout le corpus courant."""
    spec = embedder.spec
    register_model(conn, spec)
    report = EmbeddingReport(spec.key)
    after = uuid.UUID(int=0)
    params: dict[str, Any] = {
        "model": spec.key,
        "documents": list(documents) if documents else None,
        "nature": nature,
        "as_of": as_of,
    }
    while limit is None or report.versions < limit:
        size = batch if limit is None else min(batch, limit - report.versions)
        rows = conn.execute(_CANDIDATES, params | {"after": after, "n": size}).fetchall()
        if not rows:
            break
        after = rows[-1][0]
        passages = {row[0]: passage_text(row[1], row[2] or [], row[3], row[4]) for row in rows}
        hashes = {version_id: input_sha256(spec, text) for version_id, text in passages.items()}
        known = {
            r[0]
            for r in conn.execute(
                "SELECT input_sha256 FROM embedding_vector WHERE model_key = %s AND input_sha256 = ANY(%s)",
                (spec.key, list(set(hashes.values()))),
            ).fetchall()
        }
        todo: dict[str, str] = {}
        for version_id, digest in hashes.items():
            if digest not in known:
                todo.setdefault(digest, passages[version_id])
        vectors = embedder.embed_passages(list(todo.values())) if todo else np.zeros((0, spec.dimension))
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO embedding_vector (model_key, input_sha256, embedding) VALUES (%s, %s, %s::vector)
                   ON CONFLICT DO NOTHING""",
                [(spec.key, digest, vector_literal(v)) for digest, v in zip(todo, vectors, strict=True)],
            )
            cur.executemany(
                """INSERT INTO provision_embedding (model_key, version_id, input_sha256) VALUES (%s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                [(spec.key, version_id, digest) for version_id, digest in hashes.items()],
            )
        report.versions += len(rows)
        report.computed += len(todo)
        report.reused += len(rows) - len(todo)
    return report
