"""Live updates for dashboards: an in-process fan-out of ledger changes per tenant, streamed as Server-Sent Events."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict

_listeners: dict[str, set[asyncio.Queue]] = defaultdict(set)


def notify(tenant_id: str, kind: str, **data) -> None:
    """Called after a commit; never blocks the caller (slow listeners just miss intermediate updates)."""
    for queue in list(_listeners.get(tenant_id, ())):
        if queue.full():
            continue
        queue.put_nowait({"type": kind, **data})


async def stream(tenant_id: str):
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _listeners[tenant_id].add(queue)
    try:
        yield "retry: 3000\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                yield f"event: ledger\ndata: {json.dumps(event, default=str)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # keeps proxies from closing an idle stream
    finally:
        _listeners[tenant_id].discard(queue)
