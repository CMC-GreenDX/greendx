"""Purchase Approval: a deliberately tiny second app that reuses Document Intake, the event bus and the workflow.

Purchase invoices (confident or reviewed) start the tenant's `purchase-approval` BPMN process; the outcome is
recorded here. It proves the core and the intake capability serve more than carbon accounting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import nats
import yaml
from fastapi import Depends, FastAPI, HTTPException, status

from .auth import User, current_user

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("purchase")
NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
TENANTS_DIR = Path(os.environ.get("TENANTS_DIR", "/config/tenants"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATABASE_ADMIN_URL = os.environ.get("DATABASE_ADMIN_URL", "")
PROCESS = "purchase-approval"

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS purchase;
CREATE TABLE IF NOT EXISTS purchase.request (
    id             uuid        PRIMARY KEY,
    tenant_id      text        NOT NULL,
    document_id    uuid        NOT NULL,
    invoice_number text,
    supplier       text,
    total_vnd      numeric,
    status         text        NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    decided_by     text,
    decisions      jsonb       NOT NULL DEFAULT '[]',
    created_at     timestamptz NOT NULL DEFAULT now(),
    decided_at     timestamptz,
    UNIQUE (tenant_id, document_id)
);
ALTER TABLE purchase.request ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase.request FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON purchase.request;
CREATE POLICY tenant_isolation ON purchase.request
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT USAGE ON SCHEMA purchase TO purchase_app;
GRANT SELECT, INSERT, UPDATE ON purchase.request TO purchase_app;
"""

pool: asyncpg.Pool | None = None


def _log(message: str, **context) -> None:
    log.info(json.dumps({"level": "info", "logger": "purchase", "message": message, **context}, ensure_ascii=False, default=str))


def enabled(tenant_id: str) -> bool:
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,62}$", tenant_id):
        return False
    pack = TENANTS_DIR / tenant_id
    try:
        modules = (yaml.safe_load((pack / "tenant.yaml").read_text(encoding="utf-8")) or {}).get("modules", {})
    except FileNotFoundError:
        return False
    return bool(modules.get("purchase-approval")) and (pack / "workflows" / f"{PROCESS}.bpmn").exists()


async def tx(tenant_id: str):
    conn = await pool.acquire()
    tr = conn.transaction()
    await tr.start()
    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
    return conn, tr


async def publish(js, tenant_id: str, event: str, subject_id: str, data: dict) -> None:
    event_id = str(uuid.uuid4())
    envelope = {"specversion": "1.0", "id": event_id, "source": "/apps/purchase-approval", "type": f"vn.ecotrace.{event}.v1",
                "subject": subject_id, "time": datetime.now(timezone.utc).isoformat(), "datacontenttype": "application/json",
                "tenantid": tenant_id, "traceid": uuid.uuid4().hex, "data": data}
    await js.publish(f"tenant.{tenant_id}.{event}", json.dumps(envelope, default=str).encode(),
                     headers={"Content-Type": "application/cloudevents+json", "Nats-Msg-Id": event_id})


async def on_document(js, envelope: dict, tenant_id: str) -> str:
    event = envelope["type"].removeprefix("vn.ecotrace.").removesuffix(".v1")
    data = envelope["data"]
    if data.get("document_type") != "purchase_invoice":
        return "ignored (not a purchase invoice)"
    if event == "document.extracted" and data.get("status") != "extracted":
        return "waiting for review"
    if event not in ("document.extracted", "document.reviewed"):
        return "ignored"
    if not enabled(tenant_id):
        return "ignored (purchase-approval module disabled for this tenant)"
    fields = {f["name"]: f["value"] for f in data.get("fields", [])}
    conn, tr = await tx(tenant_id)
    try:
        existing = await conn.fetchrow("SELECT id, status FROM purchase.request WHERE tenant_id = $1 AND document_id = $2",
                                       tenant_id, uuid.UUID(data["document_id"]))
        if existing:
            await tr.rollback()
            return f"request already {existing['status']}"
        request_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO purchase.request (id, tenant_id, document_id, invoice_number, supplier, total_vnd, status) "
            "VALUES ($1, $2, $3, $4, $5, $6, 'pending')", request_id, tenant_id, uuid.UUID(data["document_id"]),
            fields.get("invoice_number"), fields.get("supplier_name"),
            float(fields["total_amount_vnd"]) if fields.get("total_amount_vnd") else None)
        await tr.commit()
    except Exception:
        await tr.rollback()
        raise
    finally:
        await pool.release(conn)
    total = fields.get("total_amount_vnd") or "?"
    await publish(js, tenant_id, "workflow.requested", str(request_id), {
        "process_key": PROCESS, "business_key": str(request_id),
        "title": f"Hoá đơn {fields.get('invoice_number') or ''} · {fields.get('supplier_name') or ''}",
        "variables": {"summary": f"{fields.get('supplier_name') or '?'} · {total} VND", "documentId": data["document_id"]}})
    return "purchase request created, approval workflow requested"


async def on_workflow(envelope: dict, tenant_id: str) -> str:
    data = envelope["data"]
    if data.get("process_key") != PROCESS:
        return "ignored"
    conn, tr = await tx(tenant_id)
    try:
        await conn.execute(
            "UPDATE purchase.request SET status = $3, decided_by = $4, decisions = $5::jsonb, decided_at = now() "
            "WHERE tenant_id = $1 AND id = $2 AND status = 'pending'", tenant_id, uuid.UUID(data["business_key"]),
            "approved" if data.get("approved") else "rejected", data.get("decided_by"), json.dumps(data.get("decisions", [])))
        await tr.commit()
    except Exception:
        await tr.rollback()
        raise
    finally:
        await pool.release(conn)
    return "approved" if data.get("approved") else "rejected"


async def consume() -> None:
    while True:
        try:
            nc = await nats.connect(NATS_URL, name="purchase-approval", max_reconnect_attempts=-1)
            js = nc.jetstream()
            docs = await js.pull_subscribe("tenant.*.document.>", durable="purchase-approval", stream="ECOTRACE_EVENTS")
            flows = await js.pull_subscribe("tenant.*.workflow.completed", durable="purchase-approval-workflow", stream="ECOTRACE_EVENTS")
            while True:
                for sub, handler in ((docs, lambda e, t: on_document(js, e, t)), (flows, on_workflow)):
                    try:
                        messages = await sub.fetch(10, timeout=2)
                    except nats.errors.TimeoutError:
                        continue
                    for msg in messages:
                        envelope = json.loads(msg.data)
                        tenant_id = envelope.get("tenantid", "")
                        try:
                            outcome = "ignored (subject and tenantid disagree)" if msg.subject.split(".")[1] != tenant_id \
                                else await handler(envelope, tenant_id)
                            _log("event handled", subject=msg.subject, tenant_id=tenant_id, outcome=outcome)
                            await msg.ack()
                        except Exception as exc:  # noqa: BLE001
                            _log("event failed, will be redelivered", subject=msg.subject, error=str(exc))
                            await msg.nak(delay=10)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _log("consumer stopped, restarting in 5 s", error=str(exc))
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global pool
    admin = await asyncpg.connect(DATABASE_ADMIN_URL)
    try:
        await admin.execute(SCHEMA)
    finally:
        await admin.close()
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    task = asyncio.create_task(consume())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await pool.close()


app = FastAPI(title="EcoTrace Purchase Approval", version="0.1.0", lifespan=lifespan)


@app.get("/purchase/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/purchase/requests")
async def requests_list(user: User = Depends(current_user)) -> dict:
    if not enabled(user.tenant_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The purchase-approval module is not enabled for this tenant")
    conn, tr = await tx(user.tenant_id)
    try:
        rows = await conn.fetch(
            """SELECT r.*, d.filename FROM purchase.request r LEFT JOIN intake.document d ON d.id = r.document_id
               WHERE r.tenant_id = $1 ORDER BY r.created_at DESC""", user.tenant_id)
    finally:
        await tr.rollback()
        await pool.release(conn)
    return {"requests": [json.loads(json.dumps(dict(r), default=str)) for r in rows]}
