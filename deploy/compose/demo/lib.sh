#!/usr/bin/env bash
# Helpers shared by the demo checks. Source it: . deploy/compose/demo/lib.sh
GATEWAY_URL=${GATEWAY_URL:-http://localhost:9080}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}

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

wait_for() { # seconds command... -> output of the first non-empty run
  local seconds=$1 out; shift
  for _ in $(seq 1 "$seconds"); do
    out=$("$@")
    [ -n "$out" ] && { echo "$out"; return 0; }
    sleep 1
  done
  return 1
}

activity_json() { api "$1" /ledger/activities | jq -c --arg d "$2" '.activities[] | select(.document_id == $d)'; }
task_json() { api "$1" /workflow/tasks | jq -c --arg b "$2" '.tasks[] | select(.business_key == $b)'; }

complete_task() { # token business_key approved -> completion JSON
  local task
  task=$(wait_for 30 task_json "$1" "$2") || return 1
  api "$1" "/workflow/tasks/$(jq -r .id <<<"$task")/complete" -X POST -H 'Content-Type: application/json' \
    -d "{\"approved\": ${3:-true}, \"comment\": \"checked by demo script\"}"
}
