-- Demo data for the core slice: one generic table with rows for two tenants.
-- Tenant onboarding moves to config packs and dxctl in Phase 2.

CREATE SCHEMA IF NOT EXISTS demo;

CREATE TABLE demo.facility (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  text        NOT NULL,
    name       text        NOT NULL,
    kind       text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX facility_tenant_id_idx ON demo.facility (tenant_id);

INSERT INTO demo.facility (tenant_id, name, kind) VALUES
    ('company-a-steel',     'Hai Phong rolling mill',  'plant'),
    ('company-a-steel',     'Ba Ria electric furnace', 'plant'),
    ('company-a-steel',     'Hai Phong main meter',    'electricity meter'),
    ('company-b-logistics', 'Binh Duong warehouse',    'warehouse'),
    ('company-b-logistics', 'Da Nang truck depot',     'depot'),
    ('company-b-logistics', 'Fleet diesel tank',       'fuel tank');
