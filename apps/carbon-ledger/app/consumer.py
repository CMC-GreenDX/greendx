"""Consumes document events from NATS JetStream and turns emission-relevant documents into activity records.

Carbon Ledger is never called by Document Intake: it subscribes to the events (ADR-0003).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from decimal import Decimal, InvalidOperation

import nats

from . import config, db

log = logging.getLogger("ledger.consumer")

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
STREAM = "ECOTRACE_EVENTS"
DURABLE = "carbon-ledger"


async def handle(envelope: dict, subject: str) -> str:
    tenant_id = envelope.get("tenantid", "")
    if subject.split(".")[1] != tenant_id:
        return "ignored (subject and tenantid disagree)"
    event = envelope["type"].removeprefix("vn.ecotrace.").removesuffix(".v1")
    data = envelope["data"]
    # A confident extraction is used as is; anything else waits for a person's review.
    if event == "document.extracted" and data.get("status") != "extracted":
        return f"waiting for review (status {data.get('status')})"
    if event not in ("document.extracted", "document.reviewed"):
        return "ignored"
    try:
        tenant = config.load(tenant_id)
    except config.NotConfigured:
        return "ignored (no config pack)"
    if not tenant.enabled:
        return "ignored (carbon-ledger module disabled)"
    if not await db.tenant_active(tenant_id):
        return "ignored (tenant not active)"

    fields = {f["name"]: f["value"] for f in data.get("fields", [])}
    source = tenant.source_for(data.get("document_type", ""), fields)
    if source is None:
        return f"not an emission source ({data.get('document_type')})"
    try:
        quantity = Decimal(fields.get(source.quantity_field) or "")
    except InvalidOperation:
        return f"no usable {source.quantity_field}"
    period = config.period_of(fields)
    if period is None:
        return "no date to place the activity in a period"
    return await db.upsert_activity(tenant_id, {
        "document_id": data["document_id"], "document_type": data["document_type"], "source_id": source.id,
        "source_name": source.name, "facility_code": source.facility, "scope": source.scope, "quantity": quantity,
        "unit": source.activity_unit, "period": period, "origin_event": event,
    })


async def run() -> None:
    """Durable pull consumer: events survive restarts and each one is acknowledged after the database commit."""
    while True:
        try:
            nc = await nats.connect(NATS_URL, name="carbon-ledger", max_reconnect_attempts=-1)
            js = nc.jetstream()
            sub = await js.pull_subscribe("tenant.*.document.>", durable=DURABLE, stream=STREAM)
            log.info("consuming document events")
            while True:
                try:
                    messages = await sub.fetch(10, timeout=5)
                except nats.errors.TimeoutError:
                    continue
                for msg in messages:
                    try:
                        envelope = json.loads(msg.data)
                        outcome = await handle(envelope, msg.subject)
                        log.info("event handled", extra={"context": {"subject": msg.subject, "event_id": envelope.get("id"),
                                                                     "tenant_id": envelope.get("tenantid"), "outcome": outcome}})
                        await msg.ack()
                    except Exception:  # noqa: BLE001 - retried later; poison messages are visible in the logs
                        log.exception("event failed, will be redelivered", extra={"context": {"subject": msg.subject}})
                        await msg.nak(delay=10)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - e.g. the stream does not exist yet on a fresh stack
            log.exception("consumer stopped, restarting in 5 s")
            await asyncio.sleep(5)
