#!/usr/bin/env bash
# Phase 4 acceptance: different approval flows for Company A and B from their config packs, no code change;
# a purchase invoice goes to Purchase Approval, not Carbon Ledger. Usage: make workflow-check
set -uo pipefail
. "$(dirname "$0")/lib.sh"
failed=0
pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }

approved_co2e() { activity_json "$1" "$2" | jq -r 'select(.status == "approved") | .co2e_kg'; }
purchase_for() { api "$1" /purchase/requests | jq -c --arg d "$2" '.requests[] | select(.document_id == $d)'; }
decided_purchase() { purchase_for "$1" "$2" | jq -r 'select(.status != "pending") | .status'; }

alice=$(token_for alice); an=$(token_for an.tran); bob=$(token_for bob); binh=$(token_for binh.le)

echo "== Company A: one approval step (verify-activity.bpmn of company-a-steel)"
doc=$(upload_and_confirm "$alice" tenants/company-a-steel/seed/documents/electricity-bill-2026-09.pdf)
activity=$(wait_for 20 activity_json "$alice" "$doc")
aid=$(jq -r .id <<<"$activity")
if [ "$(jq -r .status <<<"$activity")" = pending_approval ]; then
  [ -z "$(task_json "$alice" "$aid")" ] && pass "alice (no approver role) does not see the approval task" || fail "alice sees the task"
  done=$(complete_task "$an" "$aid" true)
  [ "$(jq -r .process_finished <<<"$done")" = true ] && pass "an.tran approves in one step: process finished" || fail "A completion: $done"
  approved=$(wait_for 15 approved_co2e "$alice" "$doc")
  [ -n "$approved" ] && pass "workflow.completed consumed by Carbon Ledger: entry of $approved kg CO2e" || fail "activity not approved after the workflow"
else
  echo "     (activity already $(jq -r .status <<<"$activity") from an earlier run)"
fi

echo "== Company B: two approval steps (verify-activity.bpmn of company-b-logistics)"
doc=$(upload_and_confirm "$bob" tenants/company-b-logistics/seed/documents/electricity-bill-2026-09.pdf)
activity=$(wait_for 20 activity_json "$bob" "$doc")
aid=$(jq -r .id <<<"$activity")
if [ "$(jq -r .status <<<"$activity")" = pending_approval ]; then
  step1=$(wait_for 30 task_json "$bob" "$aid")
  [ -n "$step1" ] && pass "step 1 '$(jq -r .name <<<"$step1")' goes to the reviewer role (bob)" || fail "no step 1 task for bob"
  [ -z "$(task_json "$binh" "$aid")" ] && pass "binh.le (approver) does not see step 1" || fail "binh.le sees step 1"
  done=$(complete_task "$bob" "$aid" true)
  [ "$(jq -r .process_finished <<<"$done")" = false ] && pass "after step 1 the process continues" || fail "B step 1: $done"
  step2=$(wait_for 15 task_json "$binh" "$aid")
  [ -n "$step2" ] && pass "step 2 '$(jq -r .name <<<"$step2")' goes to the approver role (binh.le)" || fail "no step 2 task for binh.le"
  [ -z "$(task_json "$bob" "$aid")" ] && pass "bob (no approver role) cannot see step 2" || fail "bob sees step 2"
  done=$(complete_task "$binh" "$aid" true)
  [ "$(jq -r '.decisions | length' <<<"$done")" = 2 ] && pass "process finished with 2 recorded decisions ($(jq -r '[.decisions[].by] | join(" -> ")' <<<"$done"))" || fail "B step 2: $done"
else
  echo "     (activity already $(jq -r .status <<<"$activity") from an earlier run)"
fi

echo "== Purchase Approval reuses intake and workflow"
doc=$(upload_and_confirm "$alice" tenants/company-a-steel/seed/documents/purchase-invoice-0007.pdf)
request=$(wait_for 20 purchase_for "$alice" "$doc")
[ -n "$request" ] && pass "Company A purchase invoice became a purchase request ($(jq -r '"\(.supplier), \(.total_vnd) VND"' <<<"$request"))" || fail "no purchase request"
[ -z "$(activity_json "$alice" "$doc")" ] && pass "the purchase invoice did not go to Carbon Ledger" || fail "purchase invoice became an emission activity"
if [ "$(jq -r .status <<<"$request")" = pending ]; then
  complete_task "$an" "$(jq -r .id <<<"$request")" true >/dev/null
  status=$(wait_for 15 decided_purchase "$alice" "$doc")
  [ "$status" = approved ] && pass "an.tran approved the purchase in the purchase-approval process" || fail "purchase status '$status'"
fi
code=$(api "$bob" /purchase/requests -o /dev/null -w '%{http_code}')
[ "$code" = 403 ] && pass "Company B has the purchase-approval module disabled in tenant.yaml (HTTP 403)" || fail "Company B purchase returned $code"

[ "$failed" -eq 0 ] && printf '\033[32mAll workflow checks passed.\033[0m\n' || { printf '\033[31mSome workflow checks failed.\033[0m\n'; exit 1; }
