"""Reads the tenant's config pack: enabled modules, emission sources and factors. No tenant logic in code."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

TENANTS_DIR = Path(os.environ.get("TENANTS_DIR", "/config/tenants"))
_TENANT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_DATE_FIELDS = ("period_end", "period_start", "fuel_date", "issue_date", "invoice_date")


class NotConfigured(Exception):
    pass


@dataclass(frozen=True)
class Factor:
    key: str
    name: str
    value: float
    unit: str
    gas: str
    version: str
    source: str
    status: str


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    scope: int
    facility: str | None
    document_type: str
    quantity_field: str
    activity_unit: str
    factor: str
    match: dict[str, str]

    def matches(self, document_type: str, fields: dict[str, str | None]) -> bool:
        return document_type == self.document_type and all(fields.get(k) == v for k, v in self.match.items())


@dataclass(frozen=True)
class TenantLedgerConfig:
    tenant_id: str
    enabled: bool
    sources: list[Source]
    factors: dict[str, Factor]
    has_workflow: bool = False

    def source_for(self, document_type: str, fields: dict[str, str | None]) -> Source | None:
        return next((s for s in self.sources if s.matches(document_type, fields)), None)


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load(tenant_id: str) -> TenantLedgerConfig:
    if not _TENANT_ID.match(tenant_id):
        raise NotConfigured(tenant_id)
    pack = TENANTS_DIR / tenant_id
    try:
        tenant = _read(pack / "tenant.yaml")
        sources = _read(pack / "emission-sources.yaml")
        factors = _read(pack / "emission-factors.yaml")
    except FileNotFoundError as exc:
        raise NotConfigured(tenant_id) from exc
    return TenantLedgerConfig(
        tenant_id=tenant_id,
        enabled=bool(tenant.get("modules", {}).get("carbon-ledger", False)),
        sources=[Source(id=s["id"], name=s["name"], scope=s["scope"], facility=s.get("facility"),
                        document_type=s["document_type"], quantity_field=s["quantity_field"],
                        activity_unit=s["activity_unit"], factor=s["factor"], match=s.get("match", {}))
                 for s in sources.get("sources", [])],
        factors={k: Factor(key=k, name=f["name"], value=float(f["value"]), unit=f["unit"], gas=f["gas"],
                           version=f["version"], source=f["source"], status=f.get("status", "official"))
                 for k, f in factors.get("factors", {}).items()},
        has_workflow=(pack / "workflows" / "verify-activity.bpmn").exists(),
    )


def period_of(fields: dict[str, str | None]) -> str | None:
    """Reporting period (YYYY-MM) from the first date field present, end of a billing period first."""
    for name in _DATE_FIELDS:
        value = fields.get(name)
        if value and re.match(r"^\d{4}-\d{2}", value):
            return value[:7]
    return None
