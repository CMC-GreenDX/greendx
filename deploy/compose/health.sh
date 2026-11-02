#!/usr/bin/env bash
# Checks that every core service is up. Exit code 0 only when all checks pass.
set -uo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
HASURA_URL=${HASURA_URL:-http://localhost:8081}
COMPOSE=(docker compose --env-file .env -f deploy/compose/docker-compose.yml)

failed=0
check() {
  local name=$1; shift
  if "$@" >/dev/null 2>&1; then
    printf '  \033[32mOK  \033[0m %s\n' "$name"
  else
    printf '  \033[31mFAIL\033[0m %s\n' "$name"
    failed=1
  fi
}

http_ok() { curl -fsS -o /dev/null --max-time 5 "$1"; }
container_healthy() {
  [ "$(docker inspect --format '{{.State.Health.Status}}' "$("${COMPOSE[@]}" ps -q "$1")")" = healthy ]
}

echo "Core services:"
check "postgres   (container healthcheck)" container_healthy postgres
check "keycloak   (container healthcheck)" container_healthy keycloak
check "keycloak   realm discovery" http_ok "$KEYCLOAK_URL/realms/ecotrace/.well-known/openid-configuration"
check "hasura     /healthz" http_ok "$HASURA_URL/healthz"
check "apisix     gateway -> hasura" http_ok "$GATEWAY_URL/gateway/health"
nats_ok() {
  "${COMPOSE[@]}" exec -T document-intake python -c     "import urllib.request; urllib.request.urlopen('http://nats:8222/healthz?js-enabled-only=true', timeout=3)"
}
check "nats       JetStream /healthz" nats_ok
check "seaweedfs  (container healthcheck)" container_healthy seaweedfs
check "clamav     (container healthcheck)" container_healthy clamav
check "intake     (container healthcheck)" container_healthy document-intake
check "intake     gateway -> /intake/health" http_ok "$GATEWAY_URL/intake/health"
check "sealer     (container healthcheck, Trillian client)" container_healthy ledger-sealer
check "ledger     (container healthcheck)" container_healthy carbon-ledger
check "ledger     gateway -> /ledger/health" http_ok "$GATEWAY_URL/ledger/health"
flowable_ok() {
  "${COMPOSE[@]}" exec -T workflow python -c "import os, requests; requests.get(os.environ['FLOWABLE_URL'] + '/repository/deployments', auth=('rest-admin', os.environ['FLOWABLE_PASSWORD']), timeout=5).raise_for_status()"
}
check "flowable   REST API (from the workflow service)" flowable_ok
check "workflow   (container healthcheck)" container_healthy workflow
check "purchase   (container healthcheck)" container_healthy purchase-approval
check "console    gateway -> demo console" http_ok "$GATEWAY_URL/"
check "api-docs   gateway -> /api-docs/" http_ok "$GATEWAY_URL/api-docs/"

if [ "$failed" -ne 0 ]; then
  echo "Some checks failed. Inspect with: make logs"
  exit 1
fi
echo "All core services are healthy."
