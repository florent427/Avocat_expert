"""Enregistrement des traces d'exécution et des coûts.

Seules des empreintes et des métadonnées sont enregistrées : le texte des
questions et des documents client n'est jamais écrit dans les traces.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

#: Version de la table de prix ; le mode extractif n'appelle aucun fournisseur.
PRICE_TABLE_VERSION = "2026-10-none"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False))


@dataclass
class Step:
    component: str
    component_version: str
    status: str
    started_at: datetime
    finished_at: datetime
    input_sha256: str | None = None
    output_sha256: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    provider: str
    model: str
    duration_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    call_count: int = 0
    estimated_cost_micro_eur: int = 0


@dataclass
class Trace:
    operation: str
    input_text: str
    legal_as_of: date | None
    organization_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    routing: dict[str, Any] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    usage: list[Usage] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def persist_trace(conn: psycopg.Connection[Any], trace: Trace, outcome: str) -> uuid.UUID:
    trace_id = uuid.uuid4()
    finished = datetime.now(UTC)
    with conn.transaction():
        conn.execute(
            """INSERT INTO execution_trace (id, organization_id, user_id, operation, input_sha256,
                 input_length, legal_as_of, routing, outcome, started_at, finished_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                trace_id,
                trace.organization_id,
                trace.user_id,
                trace.operation,
                sha256_text(trace.input_text),
                len(trace.input_text),
                trace.legal_as_of,
                Jsonb(trace.routing),
                outcome,
                trace.started_at,
                finished,
            ),
        )
        for position, step in enumerate(trace.steps):
            conn.execute(
                """INSERT INTO execution_step (trace_id, organization_id, position, component,
                     component_version, input_sha256, output_sha256, status, detail, started_at, finished_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    trace_id,
                    trace.organization_id,
                    position,
                    step.component,
                    step.component_version,
                    step.input_sha256,
                    step.output_sha256,
                    step.status,
                    Jsonb(step.detail),
                    step.started_at,
                    step.finished_at,
                ),
            )
        for u in trace.usage:
            conn.execute(
                """INSERT INTO usage_record (organization_id, trace_id, provider, model, input_tokens,
                     output_tokens, cache_read_tokens, cache_write_tokens, call_count, duration_ms,
                     estimated_cost_micro_eur, price_table_version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    trace.organization_id,
                    trace_id,
                    u.provider,
                    u.model,
                    u.input_tokens,
                    u.output_tokens,
                    u.cache_read_tokens,
                    u.cache_write_tokens,
                    u.call_count,
                    u.duration_ms,
                    u.estimated_cost_micro_eur,
                    PRICE_TABLE_VERSION,
                ),
            )
    return trace_id
