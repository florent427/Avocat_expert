# Image de l'API : construction du moteur Rust puis exécution Python, en
# utilisateur non privilégié. Contexte de construction : racine du dépôt.
# NB : non construite dans l'environnement de développement initial (Docker
# indisponible) — validation prévue en CI (backlog INFRA-02).

FROM rust:1.97-slim-bookworm AS engine
WORKDIR /src/engine
COPY engine/ ./
RUN cargo build --release --locked

FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.11.32
RUN useradd --system --uid 10001 --home /app avx
WORKDIR /app
COPY services/api/pyproject.toml services/api/uv.lock services/api/README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY services/api/src ./src
COPY services/api/migrations ./migrations
RUN uv sync --locked --no-dev
COPY --from=engine /src/engine/target/release/lexverif /usr/local/bin/lexverif
USER avx
ENV AVX_LEXVERIF_BIN=/usr/local/bin/lexverif PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "--factory", "avocat_expert.api.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
