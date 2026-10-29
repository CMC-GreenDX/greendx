#!/usr/bin/env bash
# Brief acceptance test: a new company is onboarded from its config pack only, its user logs in and uploads a
# document, and disabling the tenant blocks it. Usage: make onboarding-check
set -uo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
PACK=${PACK:-tenants/company-c-cement}
TENANT=$(basename "$PACK")
USER_NAME=${USER_NAME:-chi.pham}
DXCTL=(docker compose --env-file .env -f deploy/compose/docker-compose.yml --profile tools run --rm -T dxctl)
failed=0
pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }
token() {
  curl -s -X POST "$KEYCLOAK_URL/realms/ecotrace/protocol/openid-connect/token" -d grant_type=password \
    -d client_id=ecotrace-cli -d username="$USER_NAME" --data-urlencode password="$DEMO_USER_PASSWORD" | jq -r '.access_token // empty'
}

out=$("${DXCTL[@]}" tenant validate tenants/company-a-steel/seed 2>&1)
[[ "$out" == *"tenant.yaml: missing"* ]] && pass "validate rejects an incomplete config pack" || fail "validate: $out"
out=$("${DXCTL[@]}" tenant validate "$PACK" 2>&1)
[[ "$out" == *"config pack is valid"* ]] && pass "validate accepts $PACK" || fail "validate: $out"

start=$(date +%s)
"${DXCTL[@]}" tenant create "$PACK" | sed 's/^/    /'
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -lt 300 ] && pass "$TENANT onboarded in ${elapsed}s from its config pack, no code change" || fail "onboarding took ${elapsed}s"

t=$(token)
[ -n "$t" ] && pass "$USER_NAME logs in through SSO" || fail "$USER_NAME cannot log in"
me=$(curl -sS "$GATEWAY_URL/intake/me" -H "Authorization: Bearer $t")
[ "$(jq -r .tenant_id <<<"$me")" = "$TENANT" ] && pass "token carries tenant $TENANT; config: $(jq -c '[.document_types[].id]' <<<"$me")" || fail "me: $me"
reply=$(curl -sS -X POST "$GATEWAY_URL/intake/documents" -H "Authorization: Bearer $t" \
  -F "file=@tenants/company-a-steel/seed/documents/electricity-bill-2026-09.pdf")
id=$(jq -r '.document.id // .duplicate_of // empty' <<<"$reply")
[ -n "$id" ] && pass "$USER_NAME uploads a document into $TENANT ($(jq -r '.document.document_type // "already uploaded"' <<<"$reply"))" || fail "upload: $reply"

"${DXCTL[@]}" tenant list | sed 's/^/    /'

"${DXCTL[@]}" tenant disable "$TENANT" | sed 's/^/    /'
code=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/intake/me" -H "Authorization: Bearer $t")
[ "$code" = 403 ] && pass "a token issued before the tenant was disabled is refused (HTTP 403)" || fail "disabled tenant still served ($code)"
[ -z "$(token)" ] && pass "users of a disabled tenant can no longer log in" || fail "disabled user could still log in"
"${DXCTL[@]}" tenant enable "$TENANT" | sed 's/^/    /'
[ -n "$(token)" ] && pass "re-enabling the tenant restores access" || fail "re-enabled user cannot log in"

[ "$failed" -eq 0 ] && printf '\033[32mOnboarding acceptance test passed.\033[0m\n' || { printf '\033[31mOnboarding acceptance test failed.\033[0m\n'; exit 1; }
