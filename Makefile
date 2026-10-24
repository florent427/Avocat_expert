# Raccourcis de développement. Prérequis : uv, cargo, node 22, PostgreSQL 16 + pgvector.
.PHONY: engine backend-check backend-test web-check tf-check check

engine:
	cd engine && cargo fmt --all -- --check && cargo clippy --all-targets -- -D warnings && cargo test

backend-check:
	cd services/api && uv run ruff check src tests scripts && uv run ruff format --check src tests scripts \
	  && uv run mypy && uv run python scripts/export_schemas.py --check

backend-test: engine
	cd services/api && LEXVERIF_BIN=$(CURDIR)/engine/target/debug/lexverif uv run pytest

web-check:
	cd apps/web && npm ci && npm audit --audit-level=high && npm run typecheck && npm run build

tf-check:
	cd infra/terraform && terraform fmt -recursive -check \
	  && cd envs/staging && terraform init -backend=false -input=false && terraform validate

check: engine backend-check backend-test web-check tf-check
