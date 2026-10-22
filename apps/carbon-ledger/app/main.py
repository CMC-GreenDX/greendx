"""HTTP API of Carbon Ledger. Reached only through the API gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from . import config, consumer, db
from .auth import User, current_user


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"level": record.levelname.lower(), "logger": record.name, "message": record.getMessage()}
        entry.update(getattr(record, "context", {}))
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("ledger")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    task = asyncio.create_task(consumer.run())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    await db.close()


app = FastAPI(title="EcoTrace Carbon Ledger", version="0.1.0", lifespan=lifespan)


async def _tenant(user: User) -> config.TenantLedgerConfig:
    if not await db.tenant_active(user.tenant_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Tenant {user.tenant_id} is not active")
    try:
        tenant = config.load(user.tenant_id)
    except config.NotConfigured as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant has no config pack") from exc
    if not tenant.enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The carbon-ledger module is not enabled for this tenant")
    return tenant


def _json(row: dict) -> dict:
    return json.loads(json.dumps(row, default=lambda v: float(v) if hasattr(v, "is_finite") else str(v)))


@app.get("/ledger/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ledger/activities")
async def activities(user: User = Depends(current_user)) -> dict:
    await _tenant(user)
    return {"activities": [_json(a) for a in await db.list_activities(user.tenant_id)],
            "can_approve": "approver" in user.roles}


@app.post("/ledger/activities/{activity_id}/approve")
async def approve(activity_id: uuid.UUID, user: User = Depends(current_user)) -> dict:
    tenant = await _tenant(user)
    user.require("approver")
    activity = await db.get_activity(user.tenant_id, activity_id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found")
    source = next((s for s in tenant.sources if s.id == activity["source_id"]), None)
    factor = tenant.factors.get(source.factor) if source else None
    if factor is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No emission factor configured for this source")
    try:
        result = await db.approve(user.tenant_id, activity_id, user.username, factor)
    except LookupError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Activity is not pending approval") from exc
    except db.PeriodClosed as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Period {exc} is closed") from exc
    log.info("activity approved", extra={"context": {"tenant_id": user.tenant_id, "activity_id": str(activity_id),
                                                     "user": user.username, "co2e_kg": str(result["co2e_kg"])}})
    return _json(result)


class Rejection(BaseModel):
    reason: str


@app.post("/ledger/activities/{activity_id}/reject")
async def reject(activity_id: uuid.UUID, body: Rejection, user: User = Depends(current_user)) -> dict:
    await _tenant(user)
    user.require("approver")
    if not await db.reject(user.tenant_id, activity_id, user.username, body.reason.strip()[:500]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Activity is not pending approval")
    return {"status": "rejected"}


@app.get("/ledger/summary")
async def summary(period: str | None = None, user: User = Depends(current_user)) -> dict:
    await _tenant(user)
    data = await db.summary(user.tenant_id, period)
    return {
        "period": period,
        "scope1_kg": float(sum(t["co2e_kg"] for t in data["totals"] if t["scope"] == 1)),
        "scope2_kg": float(sum(t["co2e_kg"] for t in data["totals"] if t["scope"] == 2)),
        "totals": [_json(t) for t in data["totals"]],
        "entries": [_json(e) for e in data["entries"]],
        "periods": [_json(p) for p in data["periods"]],
    }


@app.get("/ledger/entries/{entry_id}/lineage")
async def lineage(entry_id: uuid.UUID, user: User = Depends(current_user)) -> dict:
    await _tenant(user)
    found = await db.lineage(user.tenant_id, entry_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Emission entry not found")
    return _json(found)
