"""HTTP API of the Document Intake capability. Reached only through the API gateway."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.responses import Response

from . import db, events, extractor, scanner, storage, tenant_config
from .auth import User, current_user


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"level": record.levelname.lower(), "logger": record.name, "message": record.getMessage()}
        entry.update(getattr(record, "context", {}))
        return json.dumps(entry, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("intake")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ACCEPTED_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.connect()
    await events.connect()
    yield
    await events.close()
    await db.close()


app = FastAPI(title="EcoTrace Document Intake", version="0.1.0", lifespan=lifespan)


async def _tenant(user: User) -> tenant_config.TenantConfig:
    """The caller's tenant, only if it was onboarded with dxctl and is not disabled."""
    tenant_status = await db.tenant_status(user.tenant_id)
    if tenant_status != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Tenant {user.tenant_id} is {'disabled' if tenant_status else 'not onboarded'}")
    try:
        return tenant_config.load(user.tenant_id)
    except tenant_config.TenantNotConfigured as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Tenant {user.tenant_id} has no config pack") from exc


def _document_view(doc: dict, fields: list[dict], tenant: tenant_config.TenantConfig) -> dict:
    doc_type = tenant.document_type(doc["document_type"])
    specs = {f.name: f for f in doc_type.fields} if doc_type else {}
    return {
        "document": {
            "id": str(doc["id"]),
            "filename": doc["filename"],
            "content_type": doc["content_type"],
            "size_bytes": doc["size_bytes"],
            "status": doc["status"],
            "document_type": doc["document_type"],
            "document_type_label": doc_type.label if doc_type else None,
            "type_confidence": doc["type_confidence"],
            "extractor": doc["extractor"],
            "notes": doc.get("notes"),
            "uploaded_by": doc["uploaded_by"],
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
            "reviewed_by": doc.get("reviewed_by"),
            "reviewed_at": doc["reviewed_at"].isoformat() if doc.get("reviewed_at") else None,
        },
        "fields": [
            {
                **f,
                "label": specs[f["name"]].label if f["name"] in specs else {"en": f["name"], "vi": f["name"]},
                "type": specs[f["name"]].type if f["name"] in specs else "string",
                # Once a person has reviewed the document, every value is human-confirmed.
                "needs_review": doc["status"] != "reviewed" and f["confidence"] < tenant.review_threshold,
            }
            for f in fields
        ],
        "review_threshold": tenant.review_threshold,
    }


@app.get("/intake/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/intake/me")
async def me(user: User = Depends(current_user)) -> dict:
    tenant = await _tenant(user)
    return {
        "username": user.username,
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.name,
        "ai": {"enabled": extractor.ai_enabled(), "model": extractor.MODEL if extractor.ai_enabled() else None},
        "review_threshold": tenant.review_threshold,
        "document_types": [{"id": t.id, "label": t.label, "fields": [f.name for f in t.fields]} for t in tenant.document_types],
    }


@app.post("/intake/documents", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, user: User = Depends(current_user)) -> dict:
    tenant = await _tenant(user)
    trace_id = uuid.uuid4().hex
    pipeline: list[dict] = [{"step": "gateway", "status": "ok", "detail": f"{user.username} @ {user.tenant_id}"}]

    content_type = (file.content_type or "").split(";")[0]
    if content_type not in ACCEPTED_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"Unsupported file type {content_type}")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File larger than 10 MB")

    started = time.perf_counter()
    try:
        signature = await scanner.scan(content)
    except scanner.ScannerUnavailable as exc:
        log.error("scan unavailable", extra={"context": {"trace_id": trace_id, "tenant_id": tenant.tenant_id, "error": str(exc)}})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Malware scanner unavailable; upload refused") from exc
    if signature:
        log.warning("malware rejected", extra={"context": {"trace_id": trace_id, "tenant_id": tenant.tenant_id,
                                                           "user": user.username, "signature": signature}})
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Malware detected ({signature}); file rejected and not stored")
    pipeline.append({"step": "scan", "status": "ok", "detail": "ClamAV: clean",
                     "ms": round((time.perf_counter() - started) * 1000)})

    sha256 = hashlib.sha256(content).hexdigest()
    existing = await db.find_by_sha256(tenant.tenant_id, sha256)
    if existing:
        # Same file already uploaded by this tenant: counting it again would double the emissions.
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={
            "detail": "Duplicate document", "duplicate_of": str(existing["id"]), "filename": existing["filename"],
            "uploaded_by": existing["uploaded_by"], "created_at": existing["created_at"].isoformat(),
        })

    started = time.perf_counter()
    document_id = uuid.uuid4()
    filename = (file.filename or "upload")[:200]
    try:
        storage_uri = await storage.put(tenant.tenant_id, f"{document_id}{Path(filename).suffix.lower()[:8]}",
                                        content, content_type)
    except Exception as exc:  # noqa: BLE001 - any storage failure means we cannot accept the document
        log.error("storage failed", extra={"context": {"trace_id": trace_id, "tenant_id": tenant.tenant_id, "error": str(exc)}})
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Object storage unavailable; upload refused") from exc
    pipeline.append({"step": "store", "status": "ok", "detail": storage_uri,
                     "ms": round((time.perf_counter() - started) * 1000)})
    await _publish(pipeline, tenant.tenant_id, "document.received", str(document_id), trace_id, {
        "document_id": str(document_id), "filename": filename, "content_type": content_type,
        "size_bytes": len(content), "sha256": sha256, "storage_uri": storage_uri, "uploaded_by": user.username,
    })

    started = time.perf_counter()
    result = await extractor.extract(tenant, content, content_type)
    ai_ms = round((time.perf_counter() - started) * 1000)
    pipeline.append({"step": "classify", "status": "ok" if result.document_type != extractor.UNKNOWN else "warning",
                     "detail": f"{result.document_type} ({result.type_confidence:.0%})", "ms": ai_ms})
    low = [f.name for f in result.fields if f.confidence < tenant.review_threshold]
    pipeline.append({"step": "extract", "status": "warning" if low or not result.fields else "ok",
                     "detail": f"{len(result.fields)} fields, {len(low)} below {tenant.review_threshold:.0%}",
                     "extractor": result.extractor})

    if result.document_type == extractor.UNKNOWN:
        doc_status = "unrecognised"
    elif low:
        doc_status = "needs_review"
    else:
        doc_status = "extracted"
    notes = "; ".join(filter(None, [result.notes, *result.warnings])) or None

    doc = {
        "id": document_id, "tenant_id": tenant.tenant_id, "filename": filename,
        "content_type": content_type, "size_bytes": len(content), "sha256": sha256,
        "storage_path": storage_uri, "status": doc_status, "document_type": result.document_type,
        "type_confidence": result.type_confidence, "extractor": result.extractor, "notes": notes,
        "uploaded_by": user.username,
    }
    fields = [{"name": f.name, "value": f.value, "unit": f.unit, "confidence": f.confidence} for f in result.fields]
    await db.insert_document(doc, fields)
    pipeline.append({"step": "persist", "status": "ok", "detail": f"status {doc_status}"})
    await _publish(pipeline, tenant.tenant_id, "document.extracted", str(document_id), trace_id, {
        "document_id": str(document_id), "document_type": result.document_type, "status": doc_status,
        "type_confidence": result.type_confidence, "extractor": result.extractor, "storage_uri": storage_uri,
        "fields": fields,
    })

    log.info("document processed", extra={"context": {
        "trace_id": trace_id, "tenant_id": tenant.tenant_id, "document_id": str(document_id), "user": user.username,
        "document_type": result.document_type, "status": doc_status, "extractor": result.extractor, "ai_ms": ai_ms,
    }})
    view = _document_view({**doc, "created_at": None}, fields, tenant)
    view["pipeline"] = pipeline
    view["trace_id"] = trace_id
    return view


@app.get("/intake/documents")
async def list_documents(user: User = Depends(current_user)) -> dict:
    tenant = await _tenant(user)
    docs = await db.list_documents(tenant.tenant_id)
    return {"documents": [
        {**_document_view(d, [], tenant)["document"]} for d in docs
    ]}


@app.get("/intake/documents/{document_id}")
async def get_document(document_id: uuid.UUID, user: User = Depends(current_user)) -> dict:
    tenant = await _tenant(user)
    found = await db.get_document(tenant.tenant_id, document_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    view = _document_view(*found, tenant)
    view["reviews"] = await _reviews(tenant.tenant_id, document_id)
    return view


async def _reviews(tenant_id: str, document_id: uuid.UUID) -> list[dict]:
    return [{**r, "reviewed_at": r["reviewed_at"].isoformat()} for r in await db.list_reviews(tenant_id, document_id)]


class Review(BaseModel):
    values: dict[str, str | None] = {}


@app.post("/intake/documents/{document_id}/review")
async def review(document_id: uuid.UUID, body: Review, user: User = Depends(current_user)) -> dict:
    """Corrects values and confirms the document. Values not sent are confirmed as they are."""
    tenant = await _tenant(user)
    found = await db.get_document(tenant.tenant_id, document_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    doc_type = tenant.document_type(found[0]["document_type"])
    if doc_type is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "An unrecognised document cannot be reviewed")
    specs = {f.name: f for f in doc_type.fields}
    values: dict[str, str | None] = {}
    for name, value in body.values.items():
        if name not in specs:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown field {name}")
        value = (value or "").strip() or None
        if value is not None and specs[name].type == "number":
            normalised = extractor.normalise_number(value)
            if normalised is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{name}: not a number")
            value = normalised
        values[name] = value
    await db.review_document(tenant.tenant_id, document_id, user.username, values)

    doc, fields = await db.get_document(tenant.tenant_id, document_id)
    trace_id = uuid.uuid4().hex
    published: list[dict] = []
    await _publish(published, tenant.tenant_id, "document.reviewed", str(document_id), trace_id, {
        "document_id": str(document_id), "document_type": doc["document_type"], "status": doc["status"],
        "reviewed_by": user.username, "storage_uri": doc["storage_path"], "fields": fields,
    })
    log.info("document reviewed", extra={"context": {"trace_id": trace_id, "tenant_id": tenant.tenant_id,
                                                     "document_id": str(document_id), "user": user.username}})
    view = _document_view(doc, fields, tenant)
    view["reviews"] = await _reviews(tenant.tenant_id, document_id)
    view["published"] = published
    return view


@app.get("/intake/documents/{document_id}/file")
async def get_file(document_id: uuid.UUID, user: User = Depends(current_user)) -> Response:
    await _tenant(user)
    found = await db.get_document(user.tenant_id, document_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    doc = found[0]
    if not doc["storage_path"].startswith("s3://"):  # uploaded before object storage existed
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Original file is no longer available")
    content = await storage.get(user.tenant_id, doc["storage_path"])
    return Response(content, media_type=doc["content_type"],
                    headers={"Content-Disposition": f'inline; filename="{doc["id"]}"'})


async def _publish(pipeline: list[dict], tenant_id: str, event: str, subject_id: str, trace_id: str, data: dict) -> None:
    """Publishes an event and records the outcome in the pipeline. A bus outage does not lose the upload:
    the document is already stored; republishing from a transactional outbox is a follow-up."""
    try:
        target = await events.publish(tenant_id, event, subject_id, data, trace_id)
        pipeline.append({"step": "publish", "status": "ok", "detail": target})
    except Exception as exc:  # noqa: BLE001
        log.error("event publish failed", extra={"context": {"trace_id": trace_id, "tenant_id": tenant_id,
                                                             "event": event, "error": str(exc)}})
        pipeline.append({"step": "publish", "status": "warning", "detail": f"{event} not published: {exc}"})
