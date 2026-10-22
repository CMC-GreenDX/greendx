"""Period close and seal verification.

Closing a period hashes every emission entry, combines the hashes into a period digest, and appends a leaf with
the digest and the per-entry hashes to the tenant's Trillian log (through ledger-sealer). The leaf is included
in a signed Merkle root, so it can never be rewritten. Verification recomputes the hashes from the database and
compares them with the leaf read back from Trillian: any changed, removed or added row is detected and named.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from . import db, events

SEALER_URL = os.environ.get("SEALER_URL", "http://ledger-sealer:8080")
_HASHED = ("id", "tenant_id", "activity_id", "period", "scope", "facility_code", "source_id", "quantity", "unit",
           "factor_key", "factor_value", "factor_version", "co2e_kg", "approved_by")


class SealError(Exception):
    pass


def _sealer(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(SEALER_URL + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read())
    except Exception as exc:  # noqa: BLE001 - any failure means the period is not sealed
        raise SealError(f"ledger-sealer {method} {path}: {exc}") from exc


def _canonical(value) -> str | None:
    """Same value, same text: 128572.800 and 128572.8000 must hash identically."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def entry_hash(entry: dict) -> str:
    canonical = {k: _canonical(entry[k]) for k in _HASHED}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def period_digest(hashes: dict[str, str]) -> str:
    return hashlib.sha256("\n".join(f"{k}:{hashes[k]}" for k in sorted(hashes)).encode()).hexdigest()


async def _tree_for(tenant_id: str) -> str:
    tree_id = await db.tenant_tree(tenant_id)
    if tree_id is None:
        tree_id = (await asyncio.to_thread(_sealer, "POST", "/trees"))["tree_id"]
        await db.set_tenant_tree(tenant_id, tree_id)
    return tree_id


async def close(tenant_id: str, period: str, user: str) -> dict:
    tree_id = await _tree_for(tenant_id)
    async with db.tenant_tx(tenant_id) as conn:
        state = await db.lock_period(conn, tenant_id, period)
        if state["status"] == "closed":
            raise db.PeriodClosed(period)
        pending = await conn.fetchval(
            "SELECT count(*) FROM ledger.activity_record WHERE tenant_id = $1 AND period = $2 AND status = 'pending_approval'",
            tenant_id, period)
        if pending:
            raise SealError(f"{pending} activities in {period} are still waiting for approval")
        entries = [dict(r) for r in await conn.fetch(
            "SELECT * FROM ledger.emission_entry WHERE tenant_id = $1 AND period = $2", tenant_id, period)]
        hashes = {str(e["id"]): entry_hash(e) for e in entries}
        closed_at = datetime.now(timezone.utc).isoformat()
        leaf = {"type": "ecotrace.period.seal.v1", "tenant_id": tenant_id, "period": period, "closed_by": user,
                "closed_at": closed_at, "entry_count": len(entries), "digest": period_digest(hashes), "entries": hashes}
        data = json.dumps(leaf, sort_keys=True, separators=(",", ":")).encode()
        sealed = await asyncio.to_thread(_sealer, "POST", f"/trees/{tree_id}/leaves",
                                         {"data": base64.b64encode(data).decode()})
        await conn.execute(
            """UPDATE ledger.period SET status = 'closed', closed_by = $3, closed_at = $4, entry_count = $5,
               digest = $6, tree_id = $7, leaf_index = $8, leaf_hash = $9, root_hash = $10, tree_size = $11
               WHERE tenant_id = $1 AND period = $2""",
            tenant_id, period, user, datetime.fromisoformat(closed_at), len(entries), leaf["digest"], tree_id,
            sealed["leaf_index"], sealed["leaf_hash"], sealed["root_hash"], sealed["tree_size"])
    seal = {"period": period, "entry_count": len(entries), "digest": leaf["digest"], "tree_id": tree_id,
            "leaf_index": sealed["leaf_index"], "leaf_hash": sealed["leaf_hash"], "root_hash": sealed["root_hash"],
            "tree_size": sealed["tree_size"], "closed_by": user, "closed_at": closed_at}
    await events.publish(tenant_id, "ledger.sealed", period, seal, uuid.uuid4().hex)
    return seal


async def verify(tenant_id: str, period: str) -> dict:
    async with db.tenant_tx(tenant_id) as conn:
        state = await conn.fetchrow("SELECT * FROM ledger.period WHERE tenant_id = $1 AND period = $2", tenant_id, period)
        if state is None or state["status"] != "closed":
            raise SealError(f"period {period} is not sealed")
        rows = await conn.fetch(
            """SELECT e.*, a.document_id, d.filename FROM ledger.emission_entry e
               JOIN ledger.activity_record a ON a.id = e.activity_id
               LEFT JOIN intake.document d ON d.id = a.document_id
               WHERE e.tenant_id = $1 AND e.period = $2""", tenant_id, period)
    current = {str(r["id"]): dict(r) for r in rows}
    recomputed = {k: entry_hash(v) for k, v in current.items()}

    # The authority is the leaf in Trillian, not anything stored in our own database.
    leaf_reply = await asyncio.to_thread(_sealer, "GET", f"/trees/{state['tree_id']}/leaves/{state['leaf_index']}")
    sealed = json.loads(base64.b64decode(leaf_reply["data"]))
    sealed_hashes: dict[str, str] = sealed["entries"]

    changed = [k for k in sealed_hashes if k in recomputed and recomputed[k] != sealed_hashes[k]]
    removed = [k for k in sealed_hashes if k not in recomputed]
    added = [k for k in recomputed if k not in sealed_hashes]
    describe = lambda k: {"entry_id": k, **({"source_id": current[k]["source_id"], "co2e_kg": float(current[k]["co2e_kg"]),
                                                "filename": current[k]["filename"]} if k in current else {})}
    valid = leaf_reply["included"] and not (changed or removed or added) and period_digest(recomputed) == sealed["digest"]
    return {
        "period": period, "valid": valid, "included_in_log": leaf_reply["included"],
        "sealed_digest": sealed["digest"], "recomputed_digest": period_digest(recomputed),
        "period_row_matches_log": state["digest"] == sealed["digest"],
        "entry_count": sealed["entry_count"], "tree_id": state["tree_id"], "leaf_index": state["leaf_index"],
        "tree_size": leaf_reply["tree_size"], "root_hash": leaf_reply["root_hash"],
        "closed_by": sealed["closed_by"], "closed_at": sealed["closed_at"],
        "changed": [describe(k) for k in changed], "removed": [describe(k) for k in removed], "added": [describe(k) for k in added],
    }
