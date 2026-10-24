"""Traces OpenTelemetry à liste blanche d'attributs.

Aucune instrumentation automatique : elle enregistrerait des URL, en-têtes ou
corps de requête. Les spans sont créés explicitement et seuls les attributs
de ``ALLOWED_ATTRIBUTES`` (métadonnées techniques : route, statut, durées,
compteurs, versions) sont transmis ; tout autre attribut est ignoré. Le texte
des questions, des documents ou des réponses n'est jamais un attribut.

Défense en profondeur : des bibliothèques tierces (FastAPI notamment) émettent
leurs propres spans. L'exportateur ``AllowlistSpanExporter`` filtre donc
chaque span exporté, quelle qu'en soit l'origine : attributs hors liste
retirés, événements (dont les messages d'exception) et description de statut
supprimés.

Activation : variable ``AVX_OTEL_EXPORTER_ENDPOINT`` (OTLP/HTTP). Sans elle,
les spans ne sont pas exportés.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import Status

from avocat_expert import __version__

ALLOWED_ATTRIBUTES = frozenset(
    {
        "http.request.method",
        "http.route",
        "http.response.status_code",
        "avx.operation",
        "avx.status",
        "avx.hits",
        "avx.statements",
        "avx.blocked",
        "avx.verdict",
        "avx.channel",
        "avx.engine_version",
        "avx.question_length",
    }
)
_ALLOWED_TYPES = (str, bool, int, float)

_tracer = trace.get_tracer("avocat_expert", __version__)


def filter_attributes(attributes: dict[str, Any]) -> dict[str, str | bool | int | float]:
    """Ne conserve que les attributs autorisés, de type scalaire."""
    return {k: v for k, v in attributes.items() if k in ALLOWED_ATTRIBUTES and isinstance(v, _ALLOWED_TYPES)}


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[trace.Span]:
    with _tracer.start_as_current_span(name, attributes=filter_attributes(attributes)) as current:
        yield current


def set_attributes(current: trace.Span, **attributes: Any) -> None:
    current.set_attributes(filter_attributes(attributes))


def _sanitize(original: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=original.name,
        context=original.get_span_context(),
        parent=original.parent,
        resource=original.resource,
        attributes=filter_attributes(dict(original.attributes or {})),
        events=(),
        links=(),
        kind=original.kind,
        status=Status(original.status.status_code),
        start_time=original.start_time,
        end_time=original.end_time,
        instrumentation_scope=original.instrumentation_scope,
    )


class AllowlistSpanExporter(SpanExporter):
    """Exportateur qui ne laisse sortir que des spans filtrés."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_sanitize(s) for s in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def configure_tracing(endpoint: str, environment: str, exporter: SpanExporter | None = None) -> TracerProvider | None:
    """Installe le fournisseur de traces global si un point de collecte est défini."""
    if exporter is None:
        if not endpoint:
            return None
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=endpoint)
    provider = TracerProvider(
        resource=Resource.create(
            {"service.name": "avocat-expert-api", "service.version": __version__, "deployment.environment": environment}
        )
    )
    provider.add_span_processor(BatchSpanProcessor(AllowlistSpanExporter(exporter)))
    trace.set_tracer_provider(provider)
    return provider
