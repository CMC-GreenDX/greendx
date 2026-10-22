-- Core schema: tenant registry, facilities, service roles and row-level security.
-- Idempotent; applied by the db-migrate service on every `make up`.
-- psql variables: intake_password, ledger_password.

CREATE SCHEMA IF NOT EXISTS core;

CREATE TABLE IF NOT EXISTS core.tenant (
    id         text        PRIMARY KEY,
    name       text        NOT NULL,
    status     text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.facility (
    tenant_id text NOT NULL REFERENCES core.tenant (id),
    code      text NOT NULL,
    name      text NOT NULL,
    kind      text NOT NULL,
    province  text,
    PRIMARY KEY (tenant_id, code)
);

-- Service roles: they log in, but can never bypass row-level security.
SELECT format('CREATE ROLE %I LOGIN', r) FROM unnest(ARRAY['intake_app', 'ledger_app']) AS r
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) \gexec
ALTER ROLE intake_app WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'intake_password';
ALTER ROLE ledger_app WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'ledger_password';

GRANT USAGE ON SCHEMA core TO intake_app, ledger_app;
GRANT SELECT ON core.tenant, core.facility TO intake_app, ledger_app;

-- Every request of a service runs in a transaction that sets app.tenant_id first.
-- Without it, current_setting returns NULL and no row matches: fail closed.
ALTER TABLE core.tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.tenant FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON core.tenant;
CREATE POLICY tenant_isolation ON core.tenant
    USING (id = current_setting('app.tenant_id', true));

ALTER TABLE core.facility ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.facility FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON core.facility;
CREATE POLICY tenant_isolation ON core.facility
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
