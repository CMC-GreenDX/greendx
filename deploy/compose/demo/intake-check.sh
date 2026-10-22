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

raw_upload() { # token file -> JSON response (409 body for a duplicate)
  curl -sS -X POST "$GATEWAY_URL/intake/documents" -H "Authorization: Bearer $1" -F "file=@$2"
}

upload() { # token file -> JSON document view; a duplicate resolves to the document already stored
  local reply dup
  reply=$(raw_upload "$1" "$2")
  dup=$(jq -r '.duplicate_of // empty' <<<"$reply")
  if [ -n "$dup" ]; then curl -sS "$GATEWAY_URL/intake/documents/$dup" -H "Authorization: Bearer $1"; else echo "$reply"; fi
  [ -z "$dup" ]  # exit status tells whether this was a fresh upload
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
stored=$(curl -sS "$GATEWAY_URL/intake/documents/$alice_doc/file" -H "Authorization: Bearer $alice" -o /dev/null -w '%{http_code}')
[ "$stored" = 200 ] && pass "original served from Company A's bucket" || fail "original file returned $stored"
events() { docker compose --env-file .env -f deploy/compose/docker-compose.yml exec -T document-intake python - "$@" < deploy/compose/demo/events.py; }
if [ "$(jq -r 'has("pipeline")' <<<"$result")" = true ]; then  # fresh upload, not a duplicate from an earlier run
  events company-a-steel "$alice_doc" >/dev/null && pass "document.received and document.extracted published on tenant.company-a-steel.*" || fail "events for alice's document missing"
  events company-b-logistics "$alice_doc" >/dev/null && fail "alice's document appears on Company B's subjects" || pass "alice's events are not on Company B's subjects"
else
  echo "     (events checked on the first run only; run 'make reset' for a full run)"
fi

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

code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY_URL/intake/documents" -H "Authorization: Bearer $alice" \
  -F "file=@$SAMPLES/company-a-steel/seed/documents/electricity-bill-2026-09.pdf")
[ "$code" = 409 ] && pass "same file uploaded twice by Company A is refused as a duplicate (HTTP 409)" || fail "duplicate upload returned $code"
dup_of=$(raw_upload "$bob" "$SAMPLES/company-a-steel/seed/documents/electricity-bill-2026-09.pdf" | jq -r '.duplicate_of // empty')
[ "$dup_of" != "$alice_doc" ] && pass "duplicate detection is per tenant (Company B can upload a file Company A already has)" || fail "Company B blocked by Company A's document"

review=$(curl -sS -X POST "$GATEWAY_URL/intake/documents/$alice_doc/review" -H "Authorization: Bearer $alice" \
  -H 'Content-Type: application/json' -d '{"values": {"consumption_kwh": "188.900"}}')
[ "$(jq -r .document.status <<<"$review")" = reviewed ] && [ "$(field "$review" consumption_kwh)" = 188900 ] \
  && pass "reviewer corrected 188800 -> 188900 kWh and confirmed the document" || fail "review result: $(jq -c '{s: .document.status, d: .detail}' <<<"$review")"
[ "$(jq -r '.reviews[-1] | "\(.old_value)->\(.new_value) by \(.reviewed_by)"' <<<"$review")" = "188800->188900 by alice" ] \
  && pass "correction history keeps old value, new value and reviewer" || fail "history: $(jq -c .reviews <<<"$review")"
[ "$(jq -r '.published[0].status' <<<"$review")" = ok ] && pass "document.reviewed event published" || fail "document.reviewed not published"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY_URL/intake/documents/$alice_doc/review" -H "Authorization: Bearer $bob" \
  -H 'Content-Type: application/json' -d '{"values": {}}')
[ "$code" = 404 ] && pass "bob cannot review alice's document (HTTP 404)" || fail "bob reviewing alice's document returned $code"
curl -sS -X POST "$GATEWAY_URL/intake/documents/$alice_doc/review" -H "Authorization: Bearer $alice" \
  -H 'Content-Type: application/json' -d '{"values": {"consumption_kwh": "188800"}}' >/dev/null  # restore for repeat runs

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
