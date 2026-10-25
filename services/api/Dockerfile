# Image de l'API Avocat Expert. Contexte de construction : racine du dépôt.
#   docker build -f services/api/Dockerfile -t avocat-expert/api .
# Images de base officielles Docker Hub épinglées par empreinte, écrites en
# toutes lettres pour que Dependabot les suive (il ne résout pas les ARG).
# Un miroir du démon (registry-mirrors, ex. mirror.gcr.io en CI) sert la même
# empreinte sans le quota anonyme de Docker Hub.
#
# Un certificat d'autorité supplémentaire (proxy d'entreprise) peut être fourni
# au seul moment de la construction : --secret id=extra_ca,src=<fichier.pem>.
# Il n'est jamais copié dans une couche de l'image.

FROM docker.io/library/rust:1.97-slim-bookworm@sha256:2775a09d208ff0d7c1f50490c45b62db929e87ba1dcbc3f2132ac71a704bcdd3 AS engine
WORKDIR /src/engine
COPY engine/ ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export CARGO_HTTP_CAINFO=/run/secrets/extra_ca; fi; \
    cargo build --release --locked && strip target/release/lexverif

FROM docker.io/library/python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS pybuild
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY services/api/pyproject.toml services/api/uv.lock services/api/README.md ./
COPY services/api/src ./src
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -f /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir uv==0.11.32 && uv sync --locked --no-dev --no-editable

FROM docker.io/library/python:3.13-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    AVX_LEXVERIF_BIN=/usr/local/bin/lexverif \
    AVX_MIGRATIONS_DIR=/app/migrations \
    HF_HUB_OFFLINE=1
# HF_HUB_OFFLINE : la bibliothèque huggingface_hub (dépendance de tokenizers) ne
# sert jamais ; les fichiers du modèle sont lus sur disque (avx telecharger-modele).
# Outils d'installation inutiles à l'exécution (et porteurs de vulnérabilités) : retirés.
RUN python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin avx
WORKDIR /app
COPY --from=pybuild /app/.venv /app/.venv
COPY services/api/migrations ./migrations
COPY --from=engine /src/engine/target/release/lexverif /usr/local/bin/lexverif
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
# Migrations : même image, commande `avx migrate` (tâche ponctuelle).
CMD ["uvicorn", "--factory", "avocat_expert.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
