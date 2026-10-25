#!/usr/bin/env bash
# Test de fumée de la pile locale (images construites) :
#   ingestion -> index OpenSearch -> API (rôle à moindre privilège) -> web -> Keycloak.
# Les secrets sont générés pour l'exécution et jamais écrits dans le dépôt.
# Usage : scripts/smoke-compose.sh [--no-build]
# Canal sémantique : AVX_SMOKE_MODEL_DIR=<répertoire contenant
# multilingual-e5-base@d1287505/> (fichiers obtenus par avx telecharger-modele).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="$(mktemp)"
PROJECT="avx-smoke-$$"
cleanup() {
  docker compose --env-file "$ENV_FILE" -p "$PROJECT" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$ENV_FILE"
}
trap cleanup EXIT

rand() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
API_TOKEN="$(rand)"
cat > "$ENV_FILE" <<ENV
POSTGRES_PASSWORD=$(rand)
AVX_API_DB_PASSWORD=$(rand)
KEYCLOAK_DB_PASSWORD=$(rand)
KEYCLOAK_ADMIN_USER=admin-smoke
KEYCLOAK_ADMIN_PASSWORD=$(rand)
AVX_API_TOKEN=$API_TOKEN
AVX_DEV_TOKEN_SHA256=$(printf %s "$API_TOKEN" | sha256sum | cut -d' ' -f1)
ENV
SEMANTIC=""
if [[ -n "${AVX_SMOKE_MODEL_DIR:-}" ]]; then
  SEMANTIC=1
  printf 'AVX_EMBEDDING_MODEL=multilingual-e5-base@d1287505\nAVX_MODELS_DIR=%s\n' "$AVX_SMOKE_MODEL_DIR" >> "$ENV_FILE"
fi
compose() { docker compose --env-file "$ENV_FILE" -p "$PROJECT" "$@"; }
on_error() { echo "ÉCHEC — journaux :"; compose logs --no-color --tail 40 api web keycloak 2>/dev/null || true; }
trap on_error ERR
step() { printf '\n== %s\n' "$*"; }

BUILD="--build"; [[ "${1:-}" == "--no-build" ]] && BUILD=""
step "Démarrage de la pile"
compose up -d $BUILD --wait --wait-timeout 300 postgres opensearch api web keycloak

step "Ingestion des fixtures LEGI (rôle propriétaire, tâche ponctuelle)"
PGURL="postgresql://postgres:$(grep ^POSTGRES_PASSWORD "$ENV_FILE" | cut -d= -f2-)@postgres:5432/avocat_expert"
compose run --rm -T -e AVX_DATABASE_URL="$PGURL" -v "$PWD/fixtures:/fixtures:ro" migrate \
  avx ingest-legi /fixtures/legi/LEGI_20261023-215041

if [[ -n "$SEMANTIC" ]]; then
  step "Vecteurs du corpus (modèle local, empreintes vérifiées)"
  compose run --rm -T -e AVX_DATABASE_URL="$PGURL" migrate avx calculer-embeddings
fi

step "Index de recherche OpenSearch"
compose run --rm -T -e AVX_DATABASE_URL="$PGURL" -e AVX_OPENSEARCH_URL=http://opensearch:9200 migrate \
  avx indexer-recherche --complet

step "API : authentification requise"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/v1/answer -H 'Content-Type: application/json' -d '{"question":"test"}')
[[ "$code" == "401" ]] || { echo "attendu 401, obtenu $code"; exit 1; }

step "Web -> API : réponse sourcée et vérifiée"
body=$(curl -sf -X POST http://127.0.0.1:3000/api/answer -H 'Content-Type: application/json' \
  -d '{"question":"inscription sur la liste des demandeurs d'"'"'emploi","as_of":"2026-10-24"}')
python3 - "$body" <<'PY'
import json, sys
a = json.loads(sys.argv[1])
ids = [s["citation"]["official_id"] for s in a["statements"]]
assert ids == ["LEGIARTI000048590205"], ids
assert all(s["verification"]["verdict"] == "INCERTAIN" for s in a["statements"])
assert "intelligence artificielle" in a["disclaimer"]
assert "OpenSearch" in a["search"]["ranking"], a["search"]["ranking"]
print("citations :", ids, "— classement OpenSearch")
PY

if [[ -n "$SEMANTIC" ]]; then
  step "Canal sémantique : reformulation sans le vocabulaire de l'article (SEED-014)"
  body=$(curl -sf -X POST http://127.0.0.1:3000/api/answer -H 'Content-Type: application/json' \
    -d '{"question":"Pendant combien de temps l'"'"'allocation d'"'"'assurance chômage est-elle versée ?","as_of":"2026-10-24"}')
  python3 - "$body" <<'PY'
import json, sys
a = json.loads(sys.argv[1])
channels = {c["channel"]: c for c in a["search"]["channels"]}
assert channels["semantique"]["enabled"], channels["semantique"]
by_id = {h["reference"]["official_id"]: h["matched_by"] for h in a["search"]["hits"]}
assert "semantique" in by_id.get("LEGIARTI000054241899", []), by_id  # L5422-2 : durée d'indemnisation
print("L5422-2 retrouvé par :", by_id["LEGIARTI000054241899"])
PY
fi

step "Base : l'API écrit ses traces avec le rôle avx_api, sans privilège sur le corpus"
compose exec -T postgres psql -U postgres -d avocat_expert -Atc \
  "SELECT count(*) FROM execution_trace" | grep -qx 1
denied=$(compose exec -T -e PGPASSWORD="$(grep ^AVX_API_DB_PASSWORD "$ENV_FILE" | cut -d= -f2-)" postgres \
  psql -h 127.0.0.1 -U avx_api -d avocat_expert -Atc "DELETE FROM provision_version" 2>&1 || true)
grep -q "permission denied" <<<"$denied" || { echo "le rôle avx_api ne devrait pas pouvoir supprimer : $denied"; exit 1; }
echo "trace écrite ; suppression refusée au rôle avx_api"

step "Keycloak : realm importé, découverte OIDC et paramètres de sécurité"
for _ in $(seq 1 60); do curl -sf http://127.0.0.1:8080/realms/avocat-expert/.well-known/openid-configuration >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:8080/realms/avocat-expert/.well-known/openid-configuration | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d["issuer"].endswith("/realms/avocat-expert"), d["issuer"]
assert "S256" in d["code_challenge_methods_supported"]
print("issuer :", d["issuer"])'
ADMIN_PW="$(grep ^KEYCLOAK_ADMIN_PASSWORD "$ENV_FILE" | cut -d= -f2-)"
TOKEN=$(curl -sf -d client_id=admin-cli -d username=admin-smoke --data-urlencode "password=$ADMIN_PW" -d grant_type=password \
  http://127.0.0.1:8080/realms/master/protocol/openid-connect/token | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/admin/realms/avocat-expert | python3 -c '
import json, sys
r = json.load(sys.stdin)
assert r["bruteForceProtected"] and r["registrationAllowed"] is False
assert "length(12)" in r["passwordPolicy"]
print("politique de mot de passe :", r["passwordPolicy"])'
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/admin/realms/avocat-expert/authentication/required-actions/CONFIGURE_TOTP \
  | python3 -c 'import json,sys; a=json.load(sys.stdin); assert a["enabled"] and a["defaultAction"]; print("MFA (TOTP) imposée aux nouveaux comptes")'

step "Test de fumée réussi"
