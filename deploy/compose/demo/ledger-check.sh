#!/usr/bin/env bash
# End-to-end check of Carbon Ledger: document event -> activity -> approval -> emission entry -> lineage.
# Usage: make ledger-check   (needs the demo tenants: make seed)
set -uo pipefail

GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
SAMPLES=tenants/company-a-steel/seed/documents
failed=0
pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }
token_for() {
  curl -fsS -X POST "$KEYCLOAK_URL/realms/ecotrace/protocol/openid-connect/token" -d grant_type=password \
    -d client_id=ecotrace-cli -d username="$1" --data-urlencode password="$DEMO_USER_PASSWORD" | jq -r .access_token
}
api() { local t=$1; shift; curl -sS "$GATEWAY_URL$1" -H "Authorization: Bearer $t" "${@:2}"; }
upload_and_confirm() { # token file -> document id, confirmed by a reviewer so a document.reviewed event follows
  local reply id
  reply=$(api "$1" /intake/documents -X POST -F "file=@$2")
  id=$(jq -r '.document.id // .duplicate_of' <<<"$reply")
  api "$1" "/intake/documents/$id/review" -X POST -H 'Content-Type: application/json' -d '{"values": {}}' >/dev/null
  echo "$id"
}
activity_for() { # token document -> activity JSON, waiting for the event to be consumed
  for _ in $(seq 1 20); do
    a=$(api "$1" /ledger/activities | jq -c --arg d "$2" '.activities[] | select(.document_id == $d)')
    [ -n "$a" ] && { echo "$a"; return; }
    sleep 1
  done
}

alice=$(token_for alice); approver=$(token_for an.tran); bob=$(token_for bob)

doc=$(upload_and_confirm "$alice" "$SAMPLES/electricity-bill-2026-09.pdf")
activity=$(activity_for "$alice" "$doc")
[ -n "$activity" ] && pass "document.reviewed consumed: activity $(jq -r '"\(.quantity) \(.unit), scope \(.scope), \(.source_id), period \(.period), \(.status)"' <<<"$activity")" \
  || fail "no activity for the electricity bill"
activity_id=$(jq -r .id <<<"$activity")

if [ "$(jq -r .status <<<"$activity")" = pending_approval ]; then
  code=$(api "$alice" "/ledger/activities/$activity_id/approve" -X POST -o /dev/null -w '%{http_code}')
  [ "$code" = 403 ] && pass "alice (uploader, reviewer) cannot approve (HTTP 403)" || fail "alice approve returned $code"
  code=$(api "$approver" "/ledger/activities/$activity_id/approve" -X POST -o /dev/null -w '%{http_code}')
  [ "$code" = 409 ] && pass "direct approval is refused: Company A approves through its BPMN workflow (HTTP 409)" || fail "direct approve returned $code"
  . "$(dirname "$0")/lib.sh"
  complete_task "$approver" "$activity_id" true >/dev/null && echo "     approved by an.tran in My approvals"
  for _ in $(seq 1 15); do
    [ "$(api "$alice" /ledger/activities | jq -r --arg a "$activity_id" '.activities[] | select(.id == $a) | .status')" = approved ] && break
    sleep 1
  done
fi
summary=$(api "$alice" "/ledger/summary?period=2026-09")
entry_id=$(api "$alice" /ledger/activities | jq -r --arg a "$activity_id" '.activities[] | select(.id == $a) | .entry_id')
co2e=$(api "$alice" /ledger/activities | jq -r --arg a "$activity_id" '.activities[] | select(.id == $a) | .co2e_kg')
[ "$co2e" = 128572.8 ] && pass "188,800 kWh x 0.681 kgCO2e/kWh = 128.57 tCO2e (Scope 2)" || fail "co2e is '$co2e'"
echo "     summary 2026-09: scope 1 $(jq .scope1_kg <<<"$summary") kg, scope 2 $(jq .scope2_kg <<<"$summary") kg"

lineage=$(api "$alice" "/ledger/entries/$entry_id/lineage")
[ "$(jq -r .document.filename <<<"$lineage")" = electricity-bill-2026-09.pdf ] && [ "$(jq -r .activity.decided_by <<<"$lineage")" = an.tran ] \
  && pass "lineage: entry -> activity (approved by an.tran) -> $(jq -r .document.filename <<<"$lineage") (reviewed by $(jq -r .document.reviewed_by <<<"$lineage"))" \
  || fail "lineage: $(jq -c '{d: .document.filename, a: .activity.decided_by, detail}' <<<"$lineage")"
[ "$(jq -r .entry.factor_version <<<"$lineage")" = vn-grid-2024-study ] && pass "factor version and citation stored with the entry ($(jq -r .entry.factor_status <<<"$lineage"))" \
  || fail "factor: $(jq -c .entry.factor_version <<<"$lineage")"

curl -sS "$GATEWAY_URL/ledger/report?period=2026-09&format=xlsx" -H "Authorization: Bearer $alice" -o /tmp/ecotrace-report.xlsx
sheets=$(python3 -c "import zipfile,re; print(','.join(re.findall(r'name=\"([^\"]+)\"', zipfile.ZipFile('/tmp/ecotrace-report.xlsx').read('xl/workbook.xml').decode())))" 2>&1)
[[ "$sheets" == *"Chi tiết - Entries"* ]] && pass "XLSX inventory report exported (sheets: $sheets)" || fail "xlsx export: $sheets"
csv=$(curl -sS "$GATEWAY_URL/ledger/report?period=2026-09&format=csv" -H "Authorization: Bearer $alice")
grep -q "electricity-bill-2026-09.pdf" <<<"$csv" && grep -q "128.573" <<<"$csv" && pass "CSV export lists the entry with its source document and 128.573 tCO2e" || fail "csv export: $(head -c 300 <<<"$csv")"

invoice=$(upload_and_confirm "$alice" "$SAMPLES/purchase-invoice-0007.pdf")
sleep 3
[ -z "$(api "$alice" /ledger/activities | jq -r --arg d "$invoice" '.activities[] | select(.document_id == $d) | .id')" ] \
  && pass "purchase invoice creates no activity (not an emission source)" || fail "purchase invoice became an activity"

code=$(api "$bob" "/ledger/entries/$entry_id/lineage" -o /dev/null -w '%{http_code}')
[ "$code" = 404 ] && pass "bob cannot see Company A's emission entry (HTTP 404)" || fail "bob reading Company A's entry returned $code"

[ "$failed" -eq 0 ] && printf '\033[32mAll ledger checks passed.\033[0m\n' || { printf '\033[31mSome ledger checks failed.\033[0m\n'; exit 1; }
