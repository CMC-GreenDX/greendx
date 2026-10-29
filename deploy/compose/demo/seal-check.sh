#!/usr/bin/env bash
# Demo step 4 of the brief: close a period -> seal in Trillian -> tamper with one database row -> verification fails.
# Usage: make seal-check   (needs an approved entry, e.g. after make ledger-check)
set -uo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
PERIOD=${PERIOD:-2026-09}
failed=0
pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }
token_for() {
  curl -fsS -X POST "$KEYCLOAK_URL/realms/ecotrace/protocol/openid-connect/token" -d grant_type=password \
    -d client_id=ecotrace-cli -d username="$1" --data-urlencode password="$DEMO_USER_PASSWORD" | jq -r .access_token
}
api() { local t=$1; shift; curl -sS "$GATEWAY_URL$1" -H "Authorization: Bearer $t" "${@:2}"; }
as_db_owner() { # simulates someone with direct database access, bypassing every application check
  docker compose --env-file .env -f deploy/compose/docker-compose.yml exec -T postgres psql -U postgres -d ecotrace -qtAX -c "$1"
}

approver=$(token_for an.tran); alice=$(token_for alice)

. "$(dirname "$0")/lib.sh"
for id in $(api "$approver" /ledger/activities | jq -r --arg p "$PERIOD" '.activities[] | select(.period == $p and .status == "pending_approval") | .id'); do
  complete_task "$approver" "$id" true >/dev/null
done
sleep 3

status=$(api "$alice" /ledger/summary | jq -r --arg p "$PERIOD" '.periods[] | select(.period == $p) | .status')
if [ "$status" != closed ]; then
  code=$(api "$alice" "/ledger/periods/$PERIOD/close" -X POST -o /dev/null -w '%{http_code}')
  [ "$code" = 403 ] && pass "alice (not an approver) cannot close the period (HTTP 403)" || fail "alice close returned $code"
  seal=$(api "$approver" "/ledger/periods/$PERIOD/close" -X POST)
  [ "$(jq -r '.leaf_index // empty' <<<"$seal")" != "" ] \
    && pass "period $PERIOD closed by an.tran and sealed: $(jq -r '"\(.entry_count) entries, leaf #\(.leaf_index), tree size \(.tree_size), root \(.root_hash[0:16])…"' <<<"$seal")" \
    || fail "close: $seal"
fi
code=$(api "$approver" "/ledger/periods/$PERIOD/close" -X POST -o /dev/null -w '%{http_code}')
[ "$code" = 409 ] && pass "a closed period cannot be closed again (HTTP 409)" || fail "second close returned $code"

verify=$(api "$alice" "/ledger/periods/$PERIOD/verify")
[ "$(jq -r .valid <<<"$verify")" = true ] && [ "$(jq -r .included_in_log <<<"$verify")" = true ] \
  && pass "untouched data verifies against the leaf read back from Trillian (inclusion proof OK)" || fail "verify: $verify"

victim=$(as_db_owner "SELECT id FROM ledger.emission_entry WHERE tenant_id = 'company-a-steel' AND period = '$PERIOD' ORDER BY created_at LIMIT 1")
as_db_owner "UPDATE ledger.emission_entry SET co2e_kg = co2e_kg / 2 WHERE id = '$victim'" >/dev/null
echo "     tampered: halved co2e_kg of entry $victim directly in PostgreSQL"
verify=$(api "$alice" "/ledger/periods/$PERIOD/verify")
[ "$(jq -r .valid <<<"$verify")" = false ] && [ "$(jq -r '.changed[0].entry_id' <<<"$verify")" = "$victim" ] \
  && pass "verification FAILS and names the tampered entry ($(jq -r '.changed[0] | "\(.filename), now \(.co2e_kg) kg"' <<<"$verify"))" \
  || fail "tampering not detected: $(jq -c '{valid, changed}' <<<"$verify")"

as_db_owner "UPDATE ledger.emission_entry SET co2e_kg = co2e_kg * 2 WHERE id = '$victim'" >/dev/null
[ "$(api "$alice" "/ledger/periods/$PERIOD/verify" | jq -r .valid)" = true ] && pass "restoring the original value makes the seal valid again" || fail "seal still invalid after restore"

[ "$failed" -eq 0 ] && printf '\033[32mAll seal checks passed.\033[0m\n' || { printf '\033[31mSome seal checks failed.\033[0m\n'; exit 1; }
