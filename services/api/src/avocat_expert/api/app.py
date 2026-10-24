"""Application FastAPI : recherche, réponse sourcée, vérification de citation."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from avocat_expert import __version__
from avocat_expert.answer.extractive import ExtractiveAnswerService
from avocat_expert.api.security import Principal, require_principal
from avocat_expert.config import Settings, get_settings
from avocat_expert.contracts.services import (
    AnswerRequest,
    CitationVerification,
    CitationVerificationRequest,
    SearchRequest,
    SearchResponse,
    SourcedAnswer,
)
from avocat_expert.observability.telemetry import configure_tracing, set_attributes, span
from avocat_expert.observability.traces import Step, Trace, Usage, persist_trace, sha256_json
from avocat_expert.search.ports import DisabledSemanticSearcher
from avocat_expert.search.service import HybridSearchService, PostgresLexicalSearcher
from avocat_expert.storage.corpus import CorpusRepository
from avocat_expert.verification.lexverif import CitationVerifier, LexverifEngine, VerificationUnavailable

logger = logging.getLogger("avocat_expert.api")


def today() -> date:
    return datetime.now(UTC).date()


def get_connection(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[psycopg.Connection[Any]]:
    if not settings.database_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "base de données non configurée")
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        yield conn


Connection = Annotated[psycopg.Connection[Any], Depends(get_connection)]
Authenticated = Annotated[Principal, Depends(require_principal)]


def _services(conn: psycopg.Connection[Any], settings: Settings) -> tuple[HybridSearchService, CitationVerifier]:
    repository = CorpusRepository(conn)
    search = HybridSearchService(repository, PostgresLexicalSearcher(repository), DisabledSemanticSearcher())
    try:
        engine = LexverifEngine(settings.lexverif_bin, settings.lexverif_timeout_s)
    except VerificationUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return search, CitationVerifier(repository, engine)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Avocat Expert API",
        version=__version__,
        description="Recherche juridique sourcée — tranche verticale V1 (non destinée à la production).",
    )
    settings = get_settings()
    configure_tracing(settings.otel_exporter_endpoint, settings.environment)

    @app.middleware("http")
    async def trace_requests(request: Request, call_next: Any) -> Response:
        # Attributs : méthode, gabarit de route et statut uniquement (jamais l'URL ni le corps).
        with span("http.request", **{"http.request.method": request.method}) as current:
            response: Response = await call_next(request)
            route = request.scope.get("route")
            set_attributes(
                current,
                **{
                    "http.route": getattr(route, "path", "inconnue"),
                    "http.response.status_code": response.status_code,
                },
            )
            return response

    if settings.environment in ("local", "test"):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/v1/search", response_model=SearchResponse)
    def search(
        _: Authenticated, body: SearchRequest, conn: Connection, settings: Annotated[Settings, Depends(get_settings)]
    ) -> SearchResponse:
        service, _verifier = _services(conn, settings)
        return service.search(body.query, body.as_of or today(), body.limit).response

    @app.post("/v1/citations/verify", response_model=CitationVerification)
    def verify(
        _: Authenticated,
        body: CitationVerificationRequest,
        conn: Connection,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> CitationVerification:
        _search, verifier = _services(conn, settings)
        try:
            return verifier.verify(body.official_id, body.quote, body.as_of, body.territory)
        except VerificationUnavailable as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    @app.post("/v1/answer", response_model=SourcedAnswer)
    def answer(
        _: Authenticated, body: AnswerRequest, conn: Connection, settings: Annotated[Settings, Depends(get_settings)]
    ) -> SourcedAnswer:
        search_service, verifier = _services(conn, settings)
        trace = Trace(operation="answer", input_text=body.question, legal_as_of=body.as_of or today())
        trace.routing = {"mode": "EXTRACTIF", "agents": [], "motif": "tranche verticale sans modèle génératif"}
        started = datetime.now(UTC)
        with span("answer", **{"avx.operation": "answer", "avx.question_length": len(body.question)}) as current:
            try:
                result = ExtractiveAnswerService(search_service, verifier).answer(body, today())
            except VerificationUnavailable as exc:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
            set_attributes(
                current,
                **{
                    "avx.status": result.status.value,
                    "avx.statements": len(result.statements),
                    "avx.blocked": result.status.value == "BLOQUEE",
                },
            )
        finished = datetime.now(UTC)
        trace.steps.append(
            Step(
                component="extractive_answer",
                component_version=__version__,
                status="OK" if result.status.value != "BLOQUEE" else "BLOCKED",
                started_at=started,
                finished_at=finished,
                output_sha256=sha256_json(result.model_dump(mode="json")),
                detail={"statements": len(result.statements), "status": result.status.value},
            )
        )
        trace.usage.append(
            Usage(provider="none", model="none", duration_ms=int((finished - started).total_seconds() * 1000))
        )
        try:
            persist_trace(conn, trace, "BLOCKED" if result.status.value == "BLOQUEE" else "OK")
        except psycopg.Error:
            logger.exception("échec d'enregistrement de la trace")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "trace non enregistrée") from None
        return result

    return app
