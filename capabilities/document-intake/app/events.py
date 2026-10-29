"""Publishes domain events to NATS JetStream as CloudEvents 1.0 (structured JSON mode).

Subjects follow ADR-0003: tenant.<tenant_id>.<event type>, e.g. tenant.company-a-steel.document.extracted.
Consumers (Carbon Ledger, Purchase Approval) subscribe to the events; Intake never calls them directly.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import nats
from nats.js.api import RetentionPolicy, StorageType, StreamConfig

log = logging.getLogger("intake.events")

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
STREAM = os.environ.get("EVENT_STREAM", "ECOTRACE_EVENTS")
SOURCE = "/capabilities/document-intake"

_nc = None
_js = None


async def connect() -> None:
    global _nc, _js
    _nc = await nats.connect(NATS_URL, name="document-intake", max_reconnect_attempts=-1)
    _js = _nc.jetstream()
    # The stream belongs to the core; Intake only makes sure it exists so a fresh stack works.
    config = StreamConfig(name=STREAM, subjects=["tenant.*.>"], retention=RetentionPolicy.LIMITS,
                          storage=StorageType.FILE, max_age=30 * 24 * 3600, duplicate_window=120)
    try:
        await _js.stream_info(STREAM)
    except nats.js.errors.NotFoundError:
        await _js.add_stream(config)


async def close() -> None:
    if _nc is not None:
        await _nc.drain()


def subject(tenant_id: str, event: str) -> str:
    return f"tenant.{tenant_id}.{event}"


async def publish(tenant_id: str, event: str, subject_id: str, data: dict, trace_id: str) -> str:
    """Publishes one CloudEvent and returns its NATS subject. Raises on failure."""
    event_id = str(uuid.uuid4())
    envelope = {
        "specversion": "1.0",
        "id": event_id,
        "source": SOURCE,
        "type": f"vn.ecotrace.{event}.v1",
        "subject": subject_id,
        "time": datetime.now(timezone.utc).isoformat(),
        "datacontenttype": "application/json",
        "tenantid": tenant_id,
        "traceid": trace_id,
        "data": data,
    }
    target = subject(tenant_id, event)
    await _js.publish(
        target,
        json.dumps(envelope, ensure_ascii=False, default=str).encode(),
        headers={"Content-Type": "application/cloudevents+json", "Nats-Msg-Id": event_id},
    )
    return target
