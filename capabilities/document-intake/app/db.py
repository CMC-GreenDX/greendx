"""PostgreSQL access with row-level security.

Migrations run once at startup as the schema owner (DATABASE_ADMIN_URL). Requests run as `intake_app`, a role
that cannot bypass RLS, and every transaction first sets app.tenant_id: PostgreSQL itself then hides other
tenants' rows, even if a query forgets its tenant filter.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://intake_app@postgres:5432/ecotrace")
DATABASE_ADMIN_URL = os.environ.get("DATABASE_ADMIN_URL", "")

_TABLES = ["intake.document", "intake.extraction_field", "intake.field_review"]

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS intake;

CREATE TABLE IF NOT EXISTS intake.document (
    id              uuid        PRIMARY KEY,
    tenant_id       text        NOT NULL,
    filename        text        NOT NULL,
    content_type    text        NOT NULL,
    size_bytes      integer     NOT NULL,
    sha256          text        NOT NULL,
    storage_path    text        NOT NULL,
    status          text        NOT NULL,
    document_type   text,
    type_confidence real,
    extractor       text,
    notes           text,
    uploaded_by     text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    processed_at    timestamptz
);
CREATE INDEX IF NOT EXISTS document_tenant_created_idx ON intake.document (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS intake.extraction_field (
    id          bigserial PRIMARY KEY,
    document_id uuid      NOT NULL REFERENCES intake.document (id) ON DELETE CASCADE,
    tenant_id   text      NOT NULL,
    position    integer   NOT NULL,
    name        text      NOT NULL,
    value       text,
    unit        text,
    confidence  real      NOT NULL
);
CREATE INDEX IF NOT EXISTS extraction_field_document_idx ON intake.extraction_field (document_id);

ALTER TABLE intake.document ADD COLUMN IF NOT EXISTS reviewed_by text;
ALTER TABLE intake.document ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
CREATE INDEX IF NOT EXISTS document_tenant_sha_idx ON intake.document (tenant_id, sha256);

-- Every human correction is kept: who changed which value, from what, to what, and when.
CREATE TABLE IF NOT EXISTS intake.field_review (
    id          bigserial   PRIMARY KEY,
    document_id uuid        NOT NULL REFERENCES intake.document (id) ON DELETE CASCADE,
    tenant_id   text        NOT NULL,
    name        text        NOT NULL,
    old_value   text,
    new_value   text,
    reviewed_by text        NOT NULL,
    reviewed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS field_review_document_idx ON intake.field_review (document_id);

GRANT USAGE ON SCHEMA intake TO intake_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA intake TO intake_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA intake TO intake_app;
-- Carbon Ledger reads reviewed documents and their fields (lineage).
GRANT USAGE ON SCHEMA intake TO ledger_app;
GRANT SELECT ON ALL TABLES IN SCHEMA intake TO ledger_app;
"""

_RLS = """
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON {table};
CREATE POLICY tenant_isolation ON {table}
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
"""

pool: asyncpg.Pool | None = None


async def connect() -> None:
    global pool
    if DATABASE_ADMIN_URL:
        admin = await asyncpg.connect(DATABASE_ADMIN_URL)
        try:
            await admin.execute(SCHEMA + "".join(_RLS.format(table=t) for t in _TABLES))
        finally:
            await admin.close()
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)


async def close() -> None:
    if pool is not None:
        await pool.close()


@asynccontextmanager
async def tenant_tx(tenant_id: str):
    """A transaction in which PostgreSQL only shows and accepts rows of this tenant."""
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
        yield conn


async def tenant_status(tenant_id: str) -> str | None:
    async with tenant_tx(tenant_id) as conn:
        return await conn.fetchval("SELECT status FROM core.tenant WHERE id = $1", tenant_id)


async def insert_document(doc: dict, fields: list[dict]) -> None:
    async with tenant_tx(doc["tenant_id"]) as conn:
        await conn.execute(
            """
            INSERT INTO intake.document (id, tenant_id, filename, content_type, size_bytes, sha256, storage_path,
                status, document_type, type_confidence, extractor, notes, uploaded_by, processed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now())
            """,
            doc["id"], doc["tenant_id"], doc["filename"], doc["content_type"], doc["size_bytes"], doc["sha256"],
            doc["storage_path"], doc["status"], doc["document_type"], doc["type_confidence"], doc["extractor"],
            doc["notes"], doc["uploaded_by"],
        )
        await conn.executemany(
            """
            INSERT INTO intake.extraction_field (document_id, tenant_id, position, name, value, unit, confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            [(doc["id"], doc["tenant_id"], i, f["name"], f["value"], f["unit"], f["confidence"]) for i, f in enumerate(fields)],
        )


async def list_documents(tenant_id: str, limit: int = 50) -> list[dict]:
    async with tenant_tx(tenant_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, filename, content_type, size_bytes, status, document_type, type_confidence, extractor,
                   uploaded_by, created_at, reviewed_by, reviewed_at
            FROM intake.document WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2
            """,
            tenant_id, limit,
        )
    return [dict(r) for r in rows]


async def get_document(tenant_id: str, document_id: uuid.UUID) -> tuple[dict, list[dict]] | None:
    async with tenant_tx(tenant_id) as conn:
        doc = await conn.fetchrow("SELECT * FROM intake.document WHERE tenant_id = $1 AND id = $2", tenant_id, document_id)
        if doc is None:
            return None
        fields = await conn.fetch(
            "SELECT name, value, unit, confidence FROM intake.extraction_field "
            "WHERE tenant_id = $1 AND document_id = $2 ORDER BY position",
            tenant_id, document_id,
        )
    return dict(doc), [dict(f) for f in fields]


async def find_by_sha256(tenant_id: str, sha256: str) -> dict | None:
    async with tenant_tx(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT id, filename, created_at, uploaded_by FROM intake.document "
            "WHERE tenant_id = $1 AND sha256 = $2 ORDER BY created_at LIMIT 1",
            tenant_id, sha256,
        )
    return dict(row) if row else None


async def review_document(tenant_id: str, document_id: uuid.UUID, reviewer: str, values: dict[str, str | None]) -> bool:
    """Applies corrected values, records each change and marks the document reviewed. False if not found."""
    async with tenant_tx(tenant_id) as conn:
        doc = await conn.fetchrow(
            "SELECT id FROM intake.document WHERE tenant_id = $1 AND id = $2 FOR UPDATE", tenant_id, document_id)
        if doc is None:
            return False
        current = {r["name"]: r["value"] for r in await conn.fetch(
            "SELECT name, value FROM intake.extraction_field WHERE tenant_id = $1 AND document_id = $2",
            tenant_id, document_id)}
        for name, new_value in values.items():
            if name not in current or current[name] == new_value:
                continue
            await conn.execute(
                "INSERT INTO intake.field_review (document_id, tenant_id, name, old_value, new_value, reviewed_by) "
                "VALUES ($1, $2, $3, $4, $5, $6)", document_id, tenant_id, name, current[name], new_value, reviewer)
            await conn.execute(
                "UPDATE intake.extraction_field SET value = $4 WHERE tenant_id = $1 AND document_id = $2 AND name = $3",
                tenant_id, document_id, name, new_value)
        await conn.execute(
            "UPDATE intake.document SET status = 'reviewed', reviewed_by = $3, reviewed_at = now() "
            "WHERE tenant_id = $1 AND id = $2", tenant_id, document_id, reviewer)
    return True


async def list_reviews(tenant_id: str, document_id: uuid.UUID) -> list[dict]:
    async with tenant_tx(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT name, old_value, new_value, reviewed_by, reviewed_at FROM intake.field_review "
            "WHERE tenant_id = $1 AND document_id = $2 ORDER BY reviewed_at, id", tenant_id, document_id)
    return [dict(r) for r in rows]
