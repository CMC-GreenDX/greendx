#!/bin/sh
# Run by the db-migrate service on every `make up`. Idempotent.
set -eu

# 1. Core: tenant registry, service roles, row-level security.
psql -v ON_ERROR_STOP=1 -v intake_password="$INTAKE_DB_PASSWORD" -v ledger_password="$LEDGER_DB_PASSWORD" \
  -v purchase_password="$PURCHASE_DB_PASSWORD" -f /sql/core.sql

# 2. Trillian: its own role and database, so the verifiable log is separate from business data.
psql -v ON_ERROR_STOP=1 -v trillian_password="$TRILLIAN_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE trillian LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trillian') \gexec
ALTER ROLE trillian WITH LOGIN NOSUPERUSER PASSWORD :'trillian_password';
SELECT 'CREATE DATABASE trillian OWNER trillian' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'trillian') \gexec
SQL

# 3. Flowable: its own role and database; Flowable creates its tables on first start.
psql -v ON_ERROR_STOP=1 -v flowable_password="$FLOWABLE_DB_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE flowable LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'flowable') \gexec
ALTER ROLE flowable WITH LOGIN NOSUPERUSER PASSWORD :'flowable_password';
SELECT 'CREATE DATABASE flowable OWNER flowable' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'flowable') \gexec
SQL

# The upstream schema is not idempotent, so it is applied only to an empty database.
if [ -z "$(PGPASSWORD="$TRILLIAN_DB_PASSWORD" psql -U trillian -d trillian -tAc "SELECT to_regclass('public.trees')")" ]; then
  PGPASSWORD="$TRILLIAN_DB_PASSWORD" psql -v ON_ERROR_STOP=1 -q -U trillian -d trillian -f /trillian/storage.sql
  echo "Trillian schema created"
fi
