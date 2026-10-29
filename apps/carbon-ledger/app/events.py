"""Publishes ledger events (CloudEvents 1.0 on tenant.<tenant_id>.<event>, ADR-0003)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import nats

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
_nc = None


async def publish(tenant_id: str, event: str, subject_id: str, data: dict, trace_id: str) -> None:
    global _nc
    if _nc is None or not _nc.is_connected:
        _nc = await nats.connect(NATS_URL, name="carbon-ledger-publisher")
    event_id = str(uuid.uuid4())
    envelope = {"specversion": "1.0", "id": event_id, "source": "/apps/carbon-ledger", "type": f"vn.ecotrace.{event}.v1",
                "subject": subject_id, "time": datetime.now(timezone.utc).isoformat(), "datacontenttype": "application/json",
                "tenantid": tenant_id, "traceid": trace_id, "data": data}
    await _nc.jetstream().publish(f"tenant.{tenant_id}.{event}", json.dumps(envelope, default=str).encode(),
                                  headers={"Content-Type": "application/cloudevents+json", "Nats-Msg-Id": event_id})
