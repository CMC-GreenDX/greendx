"""PostgreSQL access. Every query is scoped by tenant_id; row-level security is added in Phase 2."""

from __future__ import annotations

import os
import uuid

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://postgres@postgres:5432/ecotrace")

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
"""

pool: asyncpg.Pool | None = None


async def connect() -> None:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)


async def close() -> None:
    if pool is not None:
        await pool.close()


async def insert_document(doc: dict, fields: list[dict]) -> None:
    async with pool.acquire() as conn, conn.transaction():
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
    rows = await pool.fetch(
        """
        SELECT id, filename, content_type, size_bytes, status, document_type, type_confidence, extractor,
               uploaded_by, created_at
        FROM intake.document WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT $2
        """,
        tenant_id, limit,
    )
    return [dict(r) for r in rows]


async def get_document(tenant_id: str, document_id: uuid.UUID) -> tuple[dict, list[dict]] | None:
    doc = await pool.fetchrow("SELECT * FROM intake.document WHERE tenant_id = $1 AND id = $2", tenant_id, document_id)
    if doc is None:
        return None
    fields = await pool.fetch(
        "SELECT name, value, unit, confidence FROM intake.extraction_field "
        "WHERE tenant_id = $1 AND document_id = $2 ORDER BY position",
        tenant_id, document_id,
    )
    return dict(doc), [dict(f) for f in fields]


async def find_by_sha256(tenant_id: str, sha256: str) -> dict | None:
    row = await pool.fetchrow(
        "SELECT id, filename, created_at, uploaded_by FROM intake.document "
        "WHERE tenant_id = $1 AND sha256 = $2 ORDER BY created_at LIMIT 1",
        tenant_id, sha256,
    )
    return dict(row) if row else None


async def review_document(tenant_id: str, document_id: uuid.UUID, reviewer: str, values: dict[str, str | None]) -> bool:
    """Applies corrected values, records each change and marks the document reviewed. False if not found."""
    async with pool.acquire() as conn, conn.transaction():
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
    rows = await pool.fetch(
        "SELECT name, old_value, new_value, reviewed_by, reviewed_at FROM intake.field_review "
        "WHERE tenant_id = $1 AND document_id = $2 ORDER BY reviewed_at, id", tenant_id, document_id)
    return [dict(r) for r in rows]
