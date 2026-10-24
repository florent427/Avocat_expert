"""Ligne de commande : ``avx migrate``, ``avx ingest-legi``, ``avx answer``, ``avx export-schemas``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg

from avocat_expert.config import get_settings


def _connect() -> psycopg.Connection[tuple[object, ...]]:
    url = get_settings().database_url
    if not url:
        sys.exit("AVX_DATABASE_URL non défini")
    return psycopg.connect(url, autocommit=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="avx")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="appliquer les migrations SQL")
    ingest = sub.add_parser("ingest-legi", help="ingérer une archive LEGI (.tar.gz) ou un répertoire extrait")
    ingest.add_argument("location", type=Path)
    ask = sub.add_parser("answer", help="réponse sourcée extractive")
    ask.add_argument("question")
    ask.add_argument("--as-of", type=date.fromisoformat)
    ask.add_argument("--territory")
    args = parser.parse_args(argv)

    if args.command == "migrate":
        from avocat_expert.storage.migrate import apply_migrations

        with _connect() as conn:
            print(json.dumps({"applied": apply_migrations(conn)}, ensure_ascii=False))
        return 0

    if args.command == "ingest-legi":
        from avocat_expert.connectors.legi.ingest import ingest_legi

        with _connect() as conn:
            run_id, stats = ingest_legi(conn, args.location)
        print(json.dumps({"run_id": str(run_id), **stats.as_dict()}, ensure_ascii=False))
        return 0 if stats.rejected == 0 else 1

    if args.command == "answer":
        from avocat_expert.answer.extractive import ExtractiveAnswerService
        from avocat_expert.contracts.services import AnswerRequest
        from avocat_expert.search.ports import DisabledSemanticSearcher
        from avocat_expert.search.service import HybridSearchService, PostgresLexicalSearcher
        from avocat_expert.storage.corpus import CorpusRepository
        from avocat_expert.verification.lexverif import CitationVerifier, LexverifEngine

        settings = get_settings()
        with _connect() as conn:
            repository = CorpusRepository(conn)
            service = ExtractiveAnswerService(
                HybridSearchService(repository, PostgresLexicalSearcher(repository), DisabledSemanticSearcher()),
                CitationVerifier(repository, LexverifEngine(settings.lexverif_bin, settings.lexverif_timeout_s)),
            )
            result = service.answer(
                AnswerRequest(question=args.question, as_of=args.as_of, territory=args.territory),
                datetime.now(UTC).date(),
            )
        print(result.model_dump_json(indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
