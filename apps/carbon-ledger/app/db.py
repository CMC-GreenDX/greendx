"""Ledger storage with row-level security: the service runs as ledger_app and sets app.tenant_id per transaction."""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://ledger_app@postgres:5432/ecotrace")
DATABASE_ADMIN_URL = os.environ.get("DATABASE_ADMIN_URL", "")
_TABLES = ["ledger.activity_record", "ledger.emission_entry", "ledger.period", "ledger.tenant_log"]

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS ledger;

-- One activity per source document: what was consumed, where, when, waiting for approval.
CREATE TABLE IF NOT EXISTS ledger.activity_record (
    id            uuid        PRIMARY KEY,
    tenant_id     text        NOT NULL,
    document_id   uuid        NOT NULL,
    document_type text        NOT NULL,
    source_id     text        NOT NULL,
    source_name   text        NOT NULL,
    facility_code text,
    scope         smallint    NOT NULL CHECK (scope IN (1, 2)),
    quantity      numeric     NOT NULL,
    unit          text        NOT NULL,
    period        text        NOT NULL,
    status        text        NOT NULL CHECK (status IN ('pending_approval', 'approved', 'rejected')),
    origin_event  text        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    decided_by    text,
    decided_at    timestamptz,
    reject_reason text,
    UNIQUE (tenant_id, document_id)
);

-- The emission figure, with the exact factor version that produced it.
CREATE TABLE IF NOT EXISTS ledger.emission_entry (
    id             uuid        PRIMARY KEY,
    tenant_id      text        NOT NULL,
    activity_id    uuid        NOT NULL UNIQUE REFERENCES ledger.activity_record (id),
    period         text        NOT NULL,
    scope          smallint    NOT NULL,
    facility_code  text,
    source_id      text        NOT NULL,
    quantity       numeric     NOT NULL,
    unit           text        NOT NULL,
    factor_key     text        NOT NULL,
    factor_value   numeric     NOT NULL,
    factor_unit    text        NOT NULL,
    factor_version text        NOT NULL,
    factor_source  text        NOT NULL,
    factor_status  text        NOT NULL,
    co2e_kg        numeric     NOT NULL,
    approved_by    text        NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS emission_entry_period_idx ON ledger.emission_entry (tenant_id, period);

CREATE TABLE IF NOT EXISTS ledger.period (
    tenant_id   text        NOT NULL,
    period      text        NOT NULL,
    status      text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    closed_by   text,
    closed_at   timestamptz,
    PRIMARY KEY (tenant_id, period)
);

-- Seal of a closed period: digest of its entries and where the leaf sits in the tenant's Trillian log.
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS entry_count integer;
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS digest text;
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS tree_id text;
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS leaf_index bigint;
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS leaf_hash text;
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS root_hash text;
ALTER TABLE ledger.period ADD COLUMN IF NOT EXISTS tree_size bigint;

CREATE TABLE IF NOT EXISTS ledger.tenant_log (
    tenant_id  text        PRIMARY KEY,
    tree_id    text        NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

GRANT USAGE ON SCHEMA ledger TO ledger_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ledger TO ledger_app;
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


class PeriodClosed(Exception):
    pass


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
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
        yield conn


async def _period_open(conn, tenant_id: str, period: str) -> bool:
    status = await conn.fetchval("SELECT status FROM ledger.period WHERE tenant_id = $1 AND period = $2", tenant_id, period)
    return status != "closed"


async def tenant_active(tenant_id: str) -> bool:
    async with tenant_tx(tenant_id) as conn:
        return await conn.fetchval("SELECT status FROM core.tenant WHERE id = $1", tenant_id) == "active"


async def upsert_activity(tenant_id: str, activity: dict) -> tuple[str, str | None]:
    """Creates or refreshes the activity of a document. Approved activities are never changed here.
    Returns the outcome and the id of the activity that now waits for approval (None if nothing to approve)."""
    async with tenant_tx(tenant_id) as conn:
        existing = await conn.fetchrow(
            "SELECT id, status FROM ledger.activity_record WHERE tenant_id = $1 AND document_id = $2 FOR UPDATE",
            tenant_id, activity["document_id"])
        if existing and existing["status"] == "approved":
            return "unchanged (already approved)", None
        if not await _period_open(conn, tenant_id, activity["period"]):
            return f"ignored (period {activity['period']} is closed)", None
        if existing:
            await conn.execute(
                """UPDATE ledger.activity_record SET source_id = $3, source_name = $4, facility_code = $5, scope = $6,
                   quantity = $7, unit = $8, period = $9, status = 'pending_approval', origin_event = $10,
                   updated_at = now(), decided_by = NULL, decided_at = NULL, reject_reason = NULL
                   WHERE tenant_id = $1 AND id = $2""",
                tenant_id, existing["id"], activity["source_id"], activity["source_name"], activity["facility_code"],
                activity["scope"], activity["quantity"], activity["unit"], activity["period"], activity["origin_event"])
            return "updated", str(existing["id"])
        new_id = uuid.uuid4()
        await conn.execute(
            """INSERT INTO ledger.activity_record (id, tenant_id, document_id, document_type, source_id, source_name,
               facility_code, scope, quantity, unit, period, status, origin_event)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pending_approval', $12)""",
            new_id, tenant_id, activity["document_id"], activity["document_type"], activity["source_id"],
            activity["source_name"], activity["facility_code"], activity["scope"], activity["quantity"],
            activity["unit"], activity["period"], activity["origin_event"])
        return "created", str(new_id)


async def list_activities(tenant_id: str) -> list[dict]:
    async with tenant_tx(tenant_id) as conn:
        rows = await conn.fetch(
            """SELECT a.*, d.filename, e.id AS entry_id, e.co2e_kg
               FROM ledger.activity_record a
               LEFT JOIN intake.document d ON d.id = a.document_id
               LEFT JOIN ledger.emission_entry e ON e.activity_id = a.id
               WHERE a.tenant_id = $1 ORDER BY a.created_at DESC""", tenant_id)
    return [dict(r) for r in rows]


async def get_activity(tenant_id: str, activity_id: uuid.UUID) -> dict | None:
    async with tenant_tx(tenant_id) as conn:
        row = await conn.fetchrow("SELECT * FROM ledger.activity_record WHERE tenant_id = $1 AND id = $2", tenant_id, activity_id)
    return dict(row) if row else None


async def approve(tenant_id: str, activity_id: uuid.UUID, approver: str, factor) -> dict:
    async with tenant_tx(tenant_id) as conn:
        a = await conn.fetchrow(
            "SELECT * FROM ledger.activity_record WHERE tenant_id = $1 AND id = $2 FOR UPDATE", tenant_id, activity_id)
        if a is None or a["status"] != "pending_approval":
            raise LookupError("activity not found or not pending")
        if not await _period_open(conn, tenant_id, a["period"]):
            raise PeriodClosed(a["period"])
        co2e = (a["quantity"] * Decimal(str(factor.value))).quantize(Decimal("0.001"))
        entry_id = uuid.uuid4()
        await conn.execute(
            """INSERT INTO ledger.emission_entry (id, tenant_id, activity_id, period, scope, facility_code, source_id,
               quantity, unit, factor_key, factor_value, factor_unit, factor_version, factor_source, factor_status,
               co2e_kg, approved_by)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)""",
            entry_id, tenant_id, activity_id, a["period"], a["scope"], a["facility_code"], a["source_id"],
            a["quantity"], a["unit"], factor.key, Decimal(str(factor.value)), factor.unit, factor.version,
            factor.source, factor.status, co2e, approver)
        await conn.execute(
            "UPDATE ledger.activity_record SET status = 'approved', decided_by = $3, decided_at = now(), updated_at = now() "
            "WHERE tenant_id = $1 AND id = $2", tenant_id, activity_id, approver)
    return {"entry_id": str(entry_id), "co2e_kg": co2e}


async def reject(tenant_id: str, activity_id: uuid.UUID, user: str, reason: str) -> bool:
    async with tenant_tx(tenant_id) as conn:
        result = await conn.execute(
            "UPDATE ledger.activity_record SET status = 'rejected', decided_by = $3, decided_at = now(), "
            "reject_reason = $4, updated_at = now() WHERE tenant_id = $1 AND id = $2 AND status = 'pending_approval'",
            tenant_id, activity_id, user, reason)
    return result.endswith(" 1")


async def summary(tenant_id: str, period: str | None) -> dict:
    async with tenant_tx(tenant_id) as conn:
        where, args = ("AND period = $2", [tenant_id, period]) if period else ("", [tenant_id])
        totals = await conn.fetch(
            f"""SELECT scope, facility_code, source_id, unit, count(*) AS entries, sum(quantity) AS quantity,
                sum(co2e_kg) AS co2e_kg FROM ledger.emission_entry WHERE tenant_id = $1 {where}
                GROUP BY scope, facility_code, source_id, unit ORDER BY scope, facility_code, source_id""", *args)
        entries = await conn.fetch(
            f"""SELECT e.id, e.period, e.scope, e.facility_code, e.source_id, e.quantity, e.unit, e.co2e_kg,
                e.factor_version, e.approved_by, e.created_at, d.filename
                FROM ledger.emission_entry e
                JOIN ledger.activity_record a ON a.id = e.activity_id
                LEFT JOIN intake.document d ON d.id = a.document_id
                WHERE e.tenant_id = $1 {where.replace("period", "e.period")} ORDER BY e.created_at DESC""", *args)
        periods = await conn.fetch(
            """SELECT p.period, coalesce(lp.status, 'open') AS status, lp.closed_by, lp.closed_at, lp.entry_count,
               lp.digest, lp.tree_id, lp.leaf_index, lp.root_hash, lp.tree_size
               FROM (SELECT DISTINCT period FROM ledger.activity_record WHERE tenant_id = $1) p
               LEFT JOIN ledger.period lp ON lp.tenant_id = $1 AND lp.period = p.period ORDER BY p.period DESC""",
            tenant_id)
    return {"totals": [dict(r) for r in totals], "entries": [dict(r) for r in entries], "periods": [dict(r) for r in periods]}


async def lineage(tenant_id: str, entry_id: uuid.UUID) -> dict | None:
    """emission entry -> activity -> document (fields, corrections, reviewer) -> approval -> factor."""
    async with tenant_tx(tenant_id) as conn:
        entry = await conn.fetchrow("SELECT * FROM ledger.emission_entry WHERE tenant_id = $1 AND id = $2", tenant_id, entry_id)
        if entry is None:
            return None
        activity = await conn.fetchrow("SELECT * FROM ledger.activity_record WHERE id = $1", entry["activity_id"])
        document = await conn.fetchrow(
            "SELECT id, filename, content_type, document_type, status, extractor, uploaded_by, created_at, "
            "reviewed_by, reviewed_at, sha256, storage_path FROM intake.document WHERE id = $1", activity["document_id"])
        fields = await conn.fetch(
            "SELECT name, value, unit, confidence FROM intake.extraction_field WHERE document_id = $1 ORDER BY position",
            activity["document_id"])
        corrections = await conn.fetch(
            "SELECT name, old_value, new_value, reviewed_by, reviewed_at FROM intake.field_review "
            "WHERE document_id = $1 ORDER BY reviewed_at", activity["document_id"])
        period = await conn.fetchrow("SELECT * FROM ledger.period WHERE tenant_id = $1 AND period = $2", tenant_id, entry["period"])
    return {"entry": dict(entry), "activity": dict(activity), "document": dict(document) if document else None,
            "fields": [dict(f) for f in fields], "corrections": [dict(c) for c in corrections],
            "period": dict(period) if period else {"period": entry["period"], "status": "open"}}


async def tenant_tree(tenant_id: str) -> str | None:
    async with tenant_tx(tenant_id) as conn:
        return await conn.fetchval("SELECT tree_id FROM ledger.tenant_log WHERE tenant_id = $1", tenant_id)


async def set_tenant_tree(tenant_id: str, tree_id: str) -> None:
    async with tenant_tx(tenant_id) as conn:
        await conn.execute("INSERT INTO ledger.tenant_log (tenant_id, tree_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                           tenant_id, tree_id)


async def lock_period(conn, tenant_id: str, period: str) -> dict:
    await conn.execute("INSERT INTO ledger.period (tenant_id, period) VALUES ($1, $2) ON CONFLICT DO NOTHING", tenant_id, period)
    return dict(await conn.fetchrow(
        "SELECT * FROM ledger.period WHERE tenant_id = $1 AND period = $2 FOR UPDATE", tenant_id, period))
