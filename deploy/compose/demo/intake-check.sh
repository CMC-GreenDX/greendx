#!/usr/bin/env bash
# End-to-end check of Document Intake through the gateway: upload, extraction and tenant isolation.
# Usage: make intake-check   (reads DEMO_USER_PASSWORD from .env)
set -uo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
: "${DEMO_USER_PASSWORD:?DEMO_USER_PASSWORD is not set; run through 'make intake-check'}"
SAMPLES=tenants
failed=0

pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }

token_for() {
  curl -fsS -X POST "$KEYCLOAK_URL/realms/ecotrace/protocol/openid-connect/token" \
    -d grant_type=password -d client_id=ecotrace-cli \
    -d username="$1" --data-urlencode password="$DEMO_USER_PASSWORD" | jq -r .access_token
}

upload() { # token file -> JSON response
  curl -sS -X POST "$GATEWAY_URL/intake/documents" -H "Authorization: Bearer $1" -F "file=@$2"
}

field() { # json name -> value
  jq -r --arg n "$2" '.fields[] | select(.name == $n) | .value' <<<"$1"
}

alice=$(token_for alice)
bob=$(token_for bob)

me=$(curl -sS "$GATEWAY_URL/intake/me" -H "Authorization: Bearer $alice")
echo "alice: tenant $(jq -r .tenant_id <<<"$me"), AI $(jq -c .ai <<<"$me")"

result=$(upload "$alice" "$SAMPLES/company-a-steel/seed/documents/electricity-bill-2026-09.pdf")
jq -c '{type: .document.document_type, status: .document.status, extractor: .document.extractor, fields: [.fields[] | {name, value, confidence}]}' <<<"$result"
[ "$(jq -r .document.document_type <<<"$result")" = electricity_bill ] && pass "electricity bill classified" || fail "electricity bill not classified"
[ "$(field "$result" consumption_kwh)" = 188800 ] && pass "consumption 188800 kWh extracted" || fail "consumption is '$(field "$result" consumption_kwh)'"
alice_doc=$(jq -r .document.id <<<"$result")
stored=$(jq -r '.pipeline[] | select(.step == "store") | .detail' <<<"$result")
[[ "$stored" == s3://ecotrace-company-a-steel/* ]] && pass "original stored in Company A's own bucket ($stored)" || fail "stored at '$stored'"
events() { docker compose --env-file .env -f deploy/compose/docker-compose.yml exec -T document-intake python - "$@" < deploy/compose/demo/events.py; }
events company-a-steel "$alice_doc" >/dev/null && pass "document.received and document.extracted published on tenant.company-a-steel.*" || fail "events for alice's document missing"
events company-b-logistics "$alice_doc" >/dev/null && fail "alice's document appears on Company B's subjects" || pass "alice's events are not on Company B's subjects"

result=$(upload "$alice" "$SAMPLES/company-a-steel/seed/documents/purchase-invoice-0007.pdf")
[ "$(jq -r .document.document_type <<<"$result")" = purchase_invoice ] && pass "purchase invoice classified" || fail "purchase invoice not classified"

result=$(upload "$bob" "$SAMPLES/company-b-logistics/seed/documents/electricity-bill-2026-09.pdf")
[ "$(field "$result" consumption_kwh)" = 42350 ] && pass "bob: consumption 42350 kWh extracted" || fail "bob: consumption is '$(field "$result" consumption_kwh)'"

code=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/intake/documents/$alice_doc" -H "Authorization: Bearer $bob")
[ "$code" = 404 ] && pass "bob cannot read alice's document (HTTP 404)" || fail "bob reading alice's document returned $code"
code=$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY_URL/intake/documents/$alice_doc/file" -H "Authorization: Bearer $bob")
[ "$code" = 404 ] && pass "bob cannot download alice's original file (HTTP 404)" || fail "bob downloading alice's file returned $code"
others=$(curl -sS "$GATEWAY_URL/intake/documents" -H "Authorization: Bearer $bob" | jq '[.documents[] | select(.id == "'"$alice_doc"'")] | length')
[ "$others" = 0 ] && pass "alice's document is not in bob's list" || fail "alice's document appears in bob's list"

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY_URL/intake/documents" -F "file=@$SAMPLES/company-a-steel/tenant.yaml")
[ "$code" = 401 ] && pass "upload without a token is rejected (HTTP 401)" || fail "upload without a token returned $code"

eicar='X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
code=$(printf '%s' "$eicar" | curl -s -o /tmp/eicar-reply -w '%{http_code}' -X POST "$GATEWAY_URL/intake/documents"   -H "Authorization: Bearer $alice" -F "file=@-;filename=eicar.pdf;type=application/pdf")
before=$(curl -sS "$GATEWAY_URL/intake/documents" -H "Authorization: Bearer $alice" | jq '[.documents[] | select(.filename == "eicar.pdf")] | length')
[ "$code" = 422 ] && [ "$before" = 0 ] && pass "EICAR test file rejected by ClamAV and not stored (HTTP 422)" || fail "EICAR upload returned $code, stored copies: $before"

if [ -n "${CHECK_IMAGES:-}" ]; then
  result=$(upload "$bob" "$SAMPLES/company-b-logistics/seed/documents/fuel-slip-2026-09-12.jpg")
  jq -c '{type: .document.document_type, status: .document.status, fields: [.fields[] | {name, value, confidence}]}' <<<"$result"
  [ "$(field "$result" quantity_liters)" = 185.4 ] && pass "fuel slip photo: 185.4 L extracted" || fail "fuel slip quantity is '$(field "$result" quantity_liters)'"
fi

[ "$failed" -eq 0 ] && printf '\033[32mAll intake checks passed.\033[0m\n' || { printf '\033[31mSome intake checks failed.\033[0m\n'; exit 1; }
