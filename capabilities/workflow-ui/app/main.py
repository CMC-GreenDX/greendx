"""Workflow capability [P]: runs BPMN processes from tenant config packs and serves the "My approvals" inbox.

Apps never call Flowable directly. They publish `workflow.requested` (process key, business key, variables) and
receive `workflow.completed` (outcome and every decision) on the event bus (ADR-0003).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

import nats
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from . import flowable
from .auth import User, current_user

logging.basicConfig(level=logging.INFO, format='{"level": "%(levelname)s", "logger": "%(name)s", "message": %(message)s}')
log = logging.getLogger("workflow")
NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
_nc = None


def _log(message: str, **context) -> None:
    log.info(json.dumps({"text": message, **context}, ensure_ascii=False, default=str))


async def publish(tenant_id: str, event: str, subject_id: str, data: dict) -> None:
    event_id = str(uuid.uuid4())
    envelope = {"specversion": "1.0", "id": event_id, "source": "/capabilities/workflow", "type": f"vn.ecotrace.{event}.v1",
                "subject": subject_id, "time": datetime.now(timezone.utc).isoformat(), "datacontenttype": "application/json",
                "tenantid": tenant_id, "traceid": uuid.uuid4().hex, "data": data}
    await _nc.jetstream().publish(f"tenant.{tenant_id}.{event}", json.dumps(envelope, default=str).encode(),
                                  headers={"Content-Type": "application/cloudevents+json", "Nats-Msg-Id": event_id})


async def handle_request(envelope: dict, subject: str) -> str:
    tenant_id = envelope["tenantid"]
    if subject.split(".")[1] != tenant_id:
        return "ignored (subject and tenantid disagree)"
    data = envelope["data"]
    key, business_key = data["process_key"], data["business_key"]
    if not await asyncio.to_thread(flowable.has_definition, tenant_id, key):
        # No process configured for this tenant: tell the app so it can fall back or report it.
        await publish(tenant_id, "workflow.unavailable", business_key, {"process_key": key, "business_key": business_key})
        return f"no {key} process deployed for {tenant_id}"
    if await asyncio.to_thread(flowable.active_instance, tenant_id, key, business_key):
        return "already running"
    variables = {**data.get("variables", {}), "businessKey": business_key, "requestedBy": envelope.get("source", ""),
                 "title": data.get("title", business_key), "decisions": "[]"}
    instance = await asyncio.to_thread(flowable.start, tenant_id, key, business_key, variables)
    return f"started {key} instance {instance['id']}"


async def consume() -> None:
    global _nc
    while True:
        try:
            _nc = await nats.connect(NATS_URL, name="workflow", max_reconnect_attempts=-1)
            sub = await _nc.jetstream().pull_subscribe("tenant.*.workflow.requested", durable="workflow", stream="ECOTRACE_EVENTS")
            while True:
                try:
                    messages = await sub.fetch(10, timeout=5)
                except nats.errors.TimeoutError:
                    continue
                for msg in messages:
                    try:
                        outcome = await handle_request(json.loads(msg.data), msg.subject)
                        _log("workflow request handled", subject=msg.subject, outcome=outcome)
                        await msg.ack()
                    except Exception as exc:  # noqa: BLE001 - e.g. Flowable still starting: retry later
                        _log("workflow request failed, will be redelivered", subject=msg.subject, error=str(exc))
                        await msg.nak(delay=10)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _log("consumer stopped, restarting in 5 s", error=str(exc))
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(consume())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


# The OpenAPI document sits under the service prefix so the gateway can publish it at /workflow/openapi.json;
# the interactive page is the shared one at /api-docs.
app = FastAPI(title="EcoTrace Workflow", version="0.1.0", lifespan=lifespan,
              openapi_url="/workflow/openapi.json", docs_url=None, redoc_url=None)


def _task_view(t: dict) -> dict:
    variables = {v["name"]: v.get("value") for v in t.get("variables", [])}
    return {"id": t["id"], "name": t["name"], "created": t["createTime"],
            "process_key": t["processDefinitionId"].split(":")[0], "process_instance_id": t["processInstanceId"],
            "business_key": variables.get("businessKey"), "title": variables.get("title"),
            "summary": variables.get("summary"), "document_id": variables.get("documentId"),
            "decisions": json.loads(variables.get("decisions") or "[]")}


@app.get("/workflow/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/workflow/tasks")
async def my_tasks(user: User = Depends(current_user)) -> dict:
    """Open tasks of the caller's tenant that one of the caller's roles may complete."""
    found = await asyncio.to_thread(flowable.tasks, user.tenant_id, sorted(user.roles))
    return {"tasks": [_task_view(t) for t in found]}


class Decision(BaseModel):
    approved: bool
    comment: str = ""


@app.post("/workflow/tasks/{task_id}/complete")
async def complete(task_id: str, body: Decision, user: User = Depends(current_user)) -> dict:
    t = await asyncio.to_thread(flowable.task, task_id)
    if t is None or t.get("tenantId") != user.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    groups = await asyncio.to_thread(flowable.candidate_groups, task_id)
    if not groups & user.roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires one of the roles {sorted(groups)}")
    instance_id = t["processInstanceId"]
    variables = await asyncio.to_thread(flowable.process_variables, instance_id)
    decisions = json.loads(variables.get("decisions") or "[]")
    decisions.append({"step": t["name"], "approved": body.approved, "by": user.username,
                      "comment": body.comment.strip()[:500], "at": datetime.now(timezone.utc).isoformat()})
    await asyncio.to_thread(flowable.complete, task_id, {
        "approved": body.approved, "decidedBy": user.username, "comment": body.comment.strip()[:500],
        "decisions": json.dumps(decisions, ensure_ascii=False)})
    finished = not await asyncio.to_thread(flowable.instance_running, instance_id)
    if finished:
        approved = all(d["approved"] for d in decisions)
        await publish(user.tenant_id, "workflow.completed", variables.get("businessKey", ""), {
            "process_key": t["processDefinitionId"].split(":")[0], "business_key": variables.get("businessKey"),
            "approved": approved, "decided_by": user.username, "decisions": decisions})
    _log("task completed", tenant_id=user.tenant_id, task=t["name"], user=user.username, approved=body.approved,
         process_finished=finished)
    return {"completed": True, "process_finished": finished, "decisions": decisions}
