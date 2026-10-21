#!/usr/bin/env bash
# Scripted demo of the core slice: identity -> gateway -> data, with tenant isolation.
# Usage: make demo   (reads DEMO_USER_PASSWORD from .env)
set -uo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
: "${DEMO_USER_PASSWORD:?DEMO_USER_PASSWORD is not set; run through 'make demo'}"

QUERY='{"query":"{ demo_facility(order_by: {name: asc}) { tenant_id name kind } }"}'
failed=0

title() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }
pause() { if [ "${DEMO_PAUSE:-0}" = 1 ]; then read -r -p "Press Enter to continue..." _; fi; }

token_for() {
  curl -fsS -X POST "$KEYCLOAK_URL/realms/ecotrace/protocol/openid-connect/token" \
    -d grant_type=password -d client_id=ecotrace-cli \
    -d username="$1" --data-urlencode password="$DEMO_USER_PASSWORD" | jq -r .access_token
}

claims_of() {
  local payload
  payload=$(cut -d. -f2 <<<"$1" | tr '_-' '/+')
  while [ $(( ${#payload} % 4 )) -ne 0 ]; do payload="$payload="; done
  base64 -d <<<"$payload" 2>/dev/null
}

graphql() {
  curl -sS -o /tmp/ecotrace-demo-body -w '%{http_code}' -X POST "$GATEWAY_URL/v1/graphql" \
    -H 'Content-Type: application/json' "$@" -d "$QUERY"
}

title "1. No token: the gateway rejects the call"
code=$(graphql)
echo "HTTP $code"
[ "$code" = 401 ] && pass "request without a token is rejected at the edge" || fail "expected 401, got $code"
pause

for user in alice bob; do
  case $user in
    alice) n=2; tenant=company-a-steel ;;
    bob)   n=3; tenant=company-b-logistics ;;
  esac
  title "$n. $user logs in through Keycloak (SSO) and calls the API through the gateway"
  token=$(token_for "$user")
  if [ -z "$token" ] || [ "$token" = null ]; then
    fail "could not get a token for $user"
    continue
  fi
  echo "Token claims: $(claims_of "$token" | jq -c '{iss, preferred_username, tenant_id, exp}' 2>/dev/null)"
  code=$(graphql -H "Authorization: Bearer $token")
  echo "HTTP $code"
  jq . /tmp/ecotrace-demo-body
  others=$(jq --arg t "$tenant" '[.data.demo_facility[]? | select(.tenant_id != $t)] | length' /tmp/ecotrace-demo-body)
  rows=$(jq '[.data.demo_facility[]?] | length' /tmp/ecotrace-demo-body)
  if [ "$code" = 200 ] && [ "$rows" -gt 0 ] && [ "$others" = 0 ]; then
    pass "$user sees only $tenant data ($rows rows)"
  else
    fail "$user: HTTP $code, $rows rows, $others rows from other tenants"
  fi
  pause
done

title "4. Forged token: changing the tenant claim breaks the signature"
token=$(token_for alice)
header=$(cut -d. -f1 <<<"$token")
signature=$(cut -d. -f3 <<<"$token")
forged_claims=$(claims_of "$token" | jq -c '.tenant_id = "company-b-logistics"' | base64 -w0 | tr '+/' '-_' | tr -d '=')
code=$(graphql -H "Authorization: Bearer $header.$forged_claims.$signature")
echo "HTTP $code"
[ "$code" = 401 ] && pass "a token with a modified tenant claim is rejected" || fail "expected 401, got $code"

echo
if [ "$failed" -eq 0 ]; then
  printf '\033[32mAll demo steps passed.\033[0m\n'
else
  printf '\033[31mSome demo steps failed.\033[0m\n'
  exit 1
fi
