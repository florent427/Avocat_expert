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
    ingest.add_argument(
        "--hors-sequence",
        action="store_true",
        help="désactive le contrôle d'ordre des livraisons (fixtures et livraisons de test uniquement)",
    )
    ingest.add_argument("--lot", type=int, default=1000, help="nombre de fichiers par transaction")
    sync = sub.add_parser(
        "sync-legi", help="appliquer dans l'ordre les livraisons LEGI publiées par la DILA (stock puis deltas)"
    )
    sync.add_argument("--dossier", type=Path, required=True, help="répertoire local des archives téléchargées")
    sync.add_argument("--max", type=int, default=None, help="nombre maximal de livraisons à appliquer")
    sync.add_argument("--simulation", action="store_true", help="afficher le plan sans rien télécharger ni ingérer")
    sync.add_argument("--lot", type=int, default=1000, help="nombre de fichiers par transaction")
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
            run_id, stats = ingest_legi(conn, args.location, enforce_order=not args.hors_sequence, batch_size=args.lot)
        print(json.dumps({"run_id": str(run_id), **stats.as_dict()}, ensure_ascii=False))
        return 0 if stats.rejected == 0 else 1

    if args.command == "sync-legi":
        from avocat_expert.connectors.legi import SOURCE_CODE
        from avocat_expert.connectors.legi.ingest import ingest_legi
        from avocat_expert.connectors.legi.remote import download, fetch_index, plan

        with _connect() as conn:
            row = conn.execute(
                """SELECT max(r.archive_timestamp) FROM ingestion_run r JOIN legal_source s ON s.id = r.source_id
                   WHERE s.code = %s AND r.status = 'SUCCEEDED'""",
                (SOURCE_CODE,),
            ).fetchone()
            last_applied = row[0] if row else None
            todo = plan(fetch_index(), last_applied if isinstance(last_applied, datetime) else None)
            if args.max is not None:
                todo = todo[: args.max]
            print(json.dumps({"derniere_livraison": str(last_applied), "a_appliquer": [a.name for a in todo]}))
            if args.simulation:
                return 0
            for archive in todo:
                local = download(archive, args.dossier)
                run_id, stats = ingest_legi(conn, local, batch_size=args.lot)
                print(
                    json.dumps({"archive": archive.name, "run_id": str(run_id), **stats.as_dict()}, ensure_ascii=False)
                )
                if stats.rejected:
                    return 1
        return 0

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
