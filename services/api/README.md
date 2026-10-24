# services/api — backend Python

Ingestion LEGI, recherche hybride, réponse sourcée extractive, vérification
des citations (via le moteur Rust `lexverif`), traces et coûts.

```bash
uv sync
uv run avx migrate                       # AVX_DATABASE_URL requis
uv run avx ingest-legi ../../fixtures/legi/LEGI_20261023-215041
uv run avx answer "conditions d'attribution de l'allocation d'assurance" --as-of 2026-10-24
AVX_TEST_DATABASE_URL=postgresql://postgres@localhost:5432/postgres uv run pytest
```

Voir `docs/architecture/architecture-v1.md`.
