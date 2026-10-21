"""Loads a tenant's config pack. The service holds no tenant-specific logic; everything comes from here."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TENANTS_DIR = Path(os.environ.get("TENANTS_DIR", "/config/tenants"))
_TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class TenantNotConfigured(Exception):
    pass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: dict[str, str]
    type: str = "string"
    unit: str | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class DocumentType:
    id: str
    label: dict[str, str]
    description: str
    keywords: list[str] = field(default_factory=list)
    fields: list[FieldSpec] = field(default_factory=list)


@dataclass(frozen=True)
class TenantConfig:
    tenant_id: str
    name: str
    review_threshold: float
    document_types: list[DocumentType]

    def document_type(self, type_id: str | None) -> DocumentType | None:
        return next((t for t in self.document_types if t.id == type_id), None)


def load(tenant_id: str) -> TenantConfig:
    """Reads the pack on every call, so a config change applies to the next upload without a restart."""
    if not _TENANT_ID.match(tenant_id):
        raise TenantNotConfigured(tenant_id)
    pack = TENANTS_DIR / tenant_id
    try:
        tenant = yaml.safe_load((pack / "tenant.yaml").read_text(encoding="utf-8"))
        types = yaml.safe_load((pack / "document-types.yaml").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TenantNotConfigured(tenant_id) from exc

    return TenantConfig(
        tenant_id=tenant_id,
        name=tenant.get("name", tenant_id),
        review_threshold=float(types.get("review_threshold", 0.8)),
        document_types=[
            DocumentType(
                id=t["id"],
                label=t["label"],
                description=t.get("description", ""),
                keywords=[k.lower() for k in t.get("keywords", [])],
                fields=[FieldSpec(**f) for f in t.get("fields", [])],
            )
            for t in types.get("document_types", [])
        ],
    )
