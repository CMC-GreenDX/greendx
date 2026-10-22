#!/usr/bin/env bash
# Proves that PostgreSQL itself isolates tenants for the service role (intake_app), independently of the code.
# Usage: make rls-check   (needs the demo tenants: make seed)
set -uo pipefail

: "${INTAKE_DB_PASSWORD:?INTAKE_DB_PASSWORD is not set; run through 'make rls-check'}"
failed=0
pass() { printf '\033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '\033[31mFAIL\033[0m %s\n' "$1"; failed=1; }

sql() { # tenant ('' for none), statement -> single value, or ERROR:<message>
  local setting=""
  [ -n "$1" ] && setting="SELECT set_config('app.tenant_id', '$1', true);"
  docker compose --env-file .env -f deploy/compose/docker-compose.yml exec -T -e PGPASSWORD="$INTAKE_DB_PASSWORD" postgres \
    psql -h 127.0.0.1 -U intake_app -d ecotrace -qtAX -v ON_ERROR_STOP=1 \
    -c "BEGIN; $setting" -c "$2" -c "ROLLBACK;" 2>&1 | grep -v '^$' | grep -v '^company-' | tail -1
}

bypass=$(sql "" "SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = current_user")
[ "$bypass" = f ] && pass "intake_app is neither superuser nor allowed to bypass RLS" || fail "intake_app can bypass RLS ($bypass)"

n=$(sql "" "SELECT count(*) FROM core.facility")
[ "$n" = 0 ] && pass "without a tenant set, the service role sees no rows at all (fail closed)" || fail "no tenant set, but $n facilities visible"

n=$(sql company-a-steel "SELECT count(*) FROM core.facility")
[ "$n" -gt 0 ] 2>/dev/null && pass "as Company A, its own $n facilities are visible" || fail "Company A sees '$n' facilities"

n=$(sql company-a-steel "SELECT count(*) FROM core.facility WHERE tenant_id = 'company-b-logistics'")
[ "$n" = 0 ] && pass "as Company A, a query that explicitly asks for Company B's rows returns nothing" || fail "Company A read $n of Company B's facilities"

n=$(sql company-a-steel "SELECT count(*) FROM intake.document WHERE tenant_id = 'company-b-logistics'")
[ "$n" = 0 ] && pass "as Company A, Company B's documents are invisible" || fail "Company A read $n of Company B's documents"

out=$(sql company-a-steel "INSERT INTO intake.document (id, tenant_id, filename, content_type, size_bytes, sha256, storage_path, status, uploaded_by)
  VALUES (gen_random_uuid(), 'company-b-logistics', 'forged.pdf', 'application/pdf', 1, 'x', 's3://x/y', 'extracted', 'mallory')")
[[ "$out" == *"row-level security"* ]] && pass "as Company A, writing a row for Company B is rejected by the database" || fail "forged insert: $out"

out=$(sql company-a-steel "UPDATE intake.document SET status = 'tampered' WHERE tenant_id = 'company-b-logistics'")
[ "$out" = "UPDATE 0" ] && pass "as Company A, updating Company B's documents changes nothing (UPDATE 0)" || fail "cross-tenant update: $out"

[ "$failed" -eq 0 ] && printf '\033[32mAll RLS checks passed.\033[0m\n' || { printf '\033[31mSome RLS checks failed.\033[0m\n'; exit 1; }
