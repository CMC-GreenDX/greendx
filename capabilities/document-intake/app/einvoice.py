"""Deterministic reader for Vietnamese e-invoices (GDT XML format, Decree 123/2020/ND-CP, Circular 78/2021/TT-BTC).

The XML already contains every value as data, so no OCR or AI is needed and confidence is 1.0. Element names
follow the GDT schema (HDon > DLHDon > TTChung / NDHDon); check them against real invoices of each provider.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from .extractor import ExtractedField, Extraction
from .tenant_config import TenantConfig

_FUEL = re.compile(r"(dầu|diesel|\bDO\b|xăng|gasoline|nhiên liệu)", re.IGNORECASE)
_LITRES = {"lít", "lit", "l", "litre", "liter"}


class NotAnEInvoice(Exception):
    pass


def _strip(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(node: ET.Element | None, *path: str) -> ET.Element | None:
    for name in path:
        if node is None:
            return None
        node = next((child for child in node if _strip(child.tag) == name), None)
    return node


def _text(node: ET.Element | None, *path: str) -> str | None:
    found = _find(node, *path)
    return found.text.strip() if found is not None and found.text and found.text.strip() else None


def _sum(values: list[str | None]) -> str | None:
    total = Decimal(0)
    seen = False
    for value in values:
        try:
            total += Decimal(value)
            seen = True
        except (InvalidOperation, TypeError):
            continue
    return format(total.normalize(), "f") if seen else None


def looks_like_einvoice(content: bytes) -> bool:
    head = content[:4096].decode("utf-8", errors="ignore")
    return "<HDon" in head or "DLHDon" in head


def read(tenant: TenantConfig, content: bytes) -> Extraction:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise NotAnEInvoice(f"invalid XML: {exc}") from exc
    data = root if _strip(root.tag) == "DLHDon" else _find(root, "DLHDon")
    if data is None:
        raise NotAnEInvoice("no DLHDon element")
    general, body = _find(data, "TTChung"), _find(data, "NDHDon")
    items = _find(body, "DSHHDVu")
    lines = [line for line in items if _strip(line.tag) == "HHDVu"] if items is not None else []

    kwh = [_text(line, "SLuong") for line in lines if (_text(line, "DVTinh") or "").lower() == "kwh"]
    fuel = [line for line in lines if (_text(line, "DVTinh") or "").lower() in _LITRES and _FUEL.search(_text(line, "THHDVu") or "")]
    values = {
        "invoice_number": _text(general, "SHDon"),
        "invoice_date": _text(general, "NLap"),
        "fuel_date": _text(general, "NLap"),
        "issue_date": _text(general, "NLap"),
        "supplier_name": _text(body, "NBan", "Ten"),
        "supplier_tax_code": _text(body, "NBan", "MST"),
        "customer_code": _text(body, "NMua", "MKHang"),
        "vat_amount_vnd": _text(body, "TToan", "TgTThue"),
        "total_amount_vnd": _text(body, "TToan", "TgTTTBSo"),
        "consumption_kwh": _sum(kwh),
        "quantity_liters": _sum([_text(line, "SLuong") for line in fuel]),
        "fuel_type": _text(fuel[0], "THHDVu") if fuel else None,
        "slip_number": _text(general, "SHDon"),
    }

    # The document type follows from what was bought, then must be one the tenant accepts.
    candidates = (["electricity_bill"] if kwh else []) + (["fuel_slip"] if fuel else []) + ["purchase_invoice"]
    accepted = {t.id for t in tenant.document_types}
    document_type = next((c for c in candidates if c in accepted), "unknown")
    spec = tenant.document_type(document_type)
    fields = [ExtractedField(f.name, values.get(f.name), f.unit, 1.0 if values.get(f.name) else 0.0)
              for f in (spec.fields if spec else [])]
    notes = (f"Read from e-invoice XML (form {_text(general, 'KHMSHDon') or '?'}, series {_text(general, 'KHHDon') or '?'}); "
             "digital signature not verified against the GDT yet.")
    return Extraction(document_type, 1.0 if spec else 0.0, fields, "e-invoice-xml", notes=notes)
