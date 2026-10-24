"""Les traces exportées ne contiennent que des attributs autorisés et jamais le texte des questions."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from avocat_expert.observability.telemetry import ALLOWED_ATTRIBUTES, configure_tracing, filter_attributes

pytestmark = [pytest.mark.db, pytest.mark.engine]

QUESTION = "Mon client Jean Dupont, licencié le 3 mars, a-t-il droit à l'allocation d'assurance ?"
TOKEN = "jeton-telemetrie-non-secret"


def test_filter_drops_unknown_and_non_scalar_attributes() -> None:
    assert filter_attributes({"http.route": "/v1/answer", "question": QUESTION, "avx.hits": [1, 2]}) == {
        "http.route": "/v1/answer"
    }


def test_exporter_sanitizes_third_party_spans() -> None:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    from avocat_expert.observability.telemetry import AllowlistSpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(AllowlistSpanExporter(exporter)))
    tracer = provider.get_tracer("bibliotheque.tierce")
    with tracer.start_as_current_span("tiers", attributes={"http.url": "/v1/answer?q=Dupont", "http.route": "/x"}) as s:
        s.add_event("exception", {"exception.message": QUESTION})
    (exported,) = exporter.get_finished_spans()
    assert dict(exported.attributes or {}) == {"http.route": "/x"}
    assert exported.events == ()


def test_exported_spans_leak_nothing(ingested_url: str, lexverif_bin: str) -> None:
    from avocat_expert.api.app import create_app
    from avocat_expert.config import Settings, get_settings

    exporter = InMemorySpanExporter()
    provider = configure_tracing("", "test", exporter=exporter)
    assert provider is not None
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url=ingested_url,
        lexverif_bin=lexverif_bin,
        dev_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/answer?client=Jean+Dupont",
            json={"question": QUESTION, "as_of": "2026-10-24"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 200
    provider.force_flush()
    spans = exporter.get_finished_spans()
    names = {s.name for s in spans}
    assert {"http.request", "answer"} <= names
    for s in spans:
        attributes = dict(s.attributes or {})
        assert set(attributes) <= ALLOWED_ATTRIBUTES, attributes
        dump = repr(attributes) + s.name
        assert "Dupont" not in dump and "licencié" not in dump
    request_span = next(s for s in spans if s.name == "http.request")
    assert request_span.attributes == {
        "http.request.method": "POST",
        "http.route": "/v1/answer",
        "http.response.status_code": 200,
    }
