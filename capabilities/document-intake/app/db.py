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
