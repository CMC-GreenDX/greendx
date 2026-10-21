"""Classifies a document and extracts fields, using the Claude API or a rule-based fallback.

The schema of the answer is built from the tenant's document-types.yaml, so a new document type or
field is a configuration change, not a code change.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field

import anthropic
from pypdf import PdfReader

from .tenant_config import DocumentType, TenantConfig

log = logging.getLogger("intake.extractor")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
# Classification and extraction are simple tasks; low effort keeps an upload to a few seconds.
EFFORT = os.environ.get("CLAUDE_EFFORT", "low")
UNKNOWN = "unknown"


@dataclass
class ExtractedField:
    name: str
    value: str | None
    unit: str | None
    confidence: float


@dataclass
class Extraction:
    document_type: str
    type_confidence: float
    fields: list[ExtractedField]
    extractor: str
    notes: str = ""
    warnings: list[str] = field(default_factory=list)


class ExtractionFailed(Exception):
    pass


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


async def extract(tenant: TenantConfig, content: bytes, content_type: str) -> Extraction:
    """Uses Claude when an API key is configured; falls back to rules if it is missing or the call fails."""
    if ai_enabled():
        try:
            return _normalise(tenant, await _extract_with_claude(tenant, content, content_type))
        except ExtractionFailed as exc:
            log.warning("Claude extraction failed, using rule-based fallback: %s", exc)
            result = _extract_with_rules(tenant, content, content_type)
            result.warnings.append(f"AI unavailable ({exc}); rule-based fallback used")
            return _normalise(tenant, result)
    result = _extract_with_rules(tenant, content, content_type)
    result.warnings.append("No ANTHROPIC_API_KEY configured; rule-based fallback used")
    return _normalise(tenant, result)


# --- Claude -------------------------------------------------------------------------------------

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(timeout=90.0, max_retries=2)
    return _client


def _system_prompt(tenant: TenantConfig) -> str:
    lines = [
        "You read business documents (bills, slips, invoices) for a Vietnamese company and turn them "
        "into structured data for its greenhouse-gas inventory. Documents are usually in Vietnamese.",
        "",
        "Classify the document as exactly one of the document types below, or as 'unknown' if it is none "
        "of them. Then extract only the fields listed for that type.",
        "",
        "Rules:",
        "- Return every listed field of the chosen type. Use null for a value that is not on the document; never guess.",
        "- Numbers: digits only with '.' as the decimal separator and no thousands separators "
        "(Vietnamese '1.234.567,5' becomes '1234567.5').",
        "- Dates: ISO format YYYY-MM-DD.",
        "- Confidence is between 0 and 1: how sure you are that the value is exactly what the document says. "
        "Lower it for blurry, handwritten, ambiguous or computed values.",
        "- Put anything a reviewer should know (inconsistent totals, missing stamps, unreadable parts) in notes, in English.",
        "",
        "Document types:",
    ]
    for t in tenant.document_types:
        lines.append(f"- {t.id}: {t.label.get('en', t.id)}. {t.description}")
        for f in t.fields:
            unit = f" in {f.unit}" if f.unit else ""
            lines.append(f"    - {f.name} ({f.type}{unit}): {f.label.get('en', f.name)}")
    return "\n".join(lines)


def _output_schema(tenant: TenantConfig) -> dict:
    field_names = sorted({f.name for t in tenant.document_types for f in t.fields})
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object",
        "properties": {
            "document_type": {"type": "string", "enum": [t.id for t in tenant.document_types] + [UNKNOWN]},
            "type_confidence": {"type": "number"},
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "enum": field_names},
                        "value": nullable_string,
                        "unit": nullable_string,
                        "confidence": {"type": "number"},
                    },
                    "required": ["name", "value", "unit", "confidence"],
                    "additionalProperties": False,
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["document_type", "type_confidence", "fields", "notes"],
        "additionalProperties": False,
    }


def _content_block(content: bytes, content_type: str) -> dict:
    data = base64.standard_b64encode(content).decode("ascii")
    if content_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": content_type, "data": data}}
    return {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": data}}


async def _extract_with_claude(tenant: TenantConfig, content: bytes, content_type: str) -> Extraction:
    try:
        response = await _get_client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            # On a safety decline, the API re-runs the request on Anthropic's recommended fallback model.
            extra_body={"fallbacks": "default"},
            output_config={
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": _output_schema(tenant)},
            },
            system=_system_prompt(tenant),
            messages=[
                {
                    "role": "user",
                    "content": [
                        _content_block(content, content_type),
                        {"type": "text", "text": "Classify this document and extract its fields."},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError as exc:
        raise ExtractionFailed("invalid API key") from exc
    except anthropic.RateLimitError as exc:
        raise ExtractionFailed("rate limited") from exc
    except anthropic.APIStatusError as exc:
        raise ExtractionFailed(f"API error {exc.status_code}") from exc
    except anthropic.APIConnectionError as exc:
        raise ExtractionFailed("cannot reach the API") from exc

    if response.stop_reason == "refusal":
        raise ExtractionFailed("the model declined the request")
    if response.stop_reason == "max_tokens":
        raise ExtractionFailed("the answer was cut off")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ExtractionFailed("no answer in the response")

    data = json.loads(text)
    return Extraction(
        document_type=data["document_type"],
        type_confidence=float(data["type_confidence"]),
        fields=[ExtractedField(f["name"], f["value"], f["unit"], float(f["confidence"])) for f in data["fields"]],
        extractor=response.model,
        notes=data.get("notes", ""),
    )


# --- Rule-based fallback ------------------------------------------------------------------------

def _fold(text: str) -> str:
    """Lowercase and normalise Unicode so keyword matching tolerates different encodings of diacritics."""
    return unicodedata.normalize("NFC", text).lower()


def _pdf_text(content: bytes) -> str:
    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    except Exception:  # noqa: BLE001 - a malformed PDF simply yields no text
        return ""


def _extract_with_rules(tenant: TenantConfig, content: bytes, content_type: str) -> Extraction:
    text = unicodedata.normalize("NFC", _pdf_text(content)) if content_type == "application/pdf" else ""
    if not text.strip():
        return Extraction(UNKNOWN, 0.0, [], "rules", notes="No text layer; the rule-based fallback cannot read images.")

    folded = _fold(text)
    best: tuple[float, DocumentType | None] = (0.0, None)
    for doc_type in tenant.document_types:
        if doc_type.keywords:
            score = sum(1 for k in doc_type.keywords if k in folded) / len(doc_type.keywords)
            if score > best[0]:
                best = (score, doc_type)
    score, doc_type = best
    if doc_type is None or score < 0.5:
        return Extraction(UNKNOWN, round(score, 2), [], "rules")

    fields = []
    for spec in doc_type.fields:
        match = re.search(spec.pattern, text, flags=re.IGNORECASE) if spec.pattern else None
        value = match.group(1).strip() if match else None
        fields.append(ExtractedField(spec.name, value, spec.unit, 0.6 if value else 0.0))
    return Extraction(doc_type.id, round(min(score, 0.7), 2), fields, "rules")


# --- Normalisation ------------------------------------------------------------------------------

def _to_number(value: str) -> str | None:
    cleaned = re.sub(r"[^\d.,-]", "", value)
    if not cleaned:
        return None
    if "," in cleaned:  # Vietnamese: '.' thousands, ',' decimals
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        float(cleaned)
    except ValueError:
        return None
    return cleaned


def _to_iso_date(value: str) -> str:
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", value.strip())
    return f"{match[3]}-{int(match[2]):02d}-{int(match[1]):02d}" if match else value


def _normalise(tenant: TenantConfig, result: Extraction) -> Extraction:
    """Keeps only fields the tenant configured for the detected type, in config order, with typed values."""
    doc_type = tenant.document_type(result.document_type)
    if doc_type is None:
        result.document_type, result.fields = UNKNOWN, []
        return result
    by_name = {f.name: f for f in result.fields}
    fields = []
    for spec in doc_type.fields:
        found = by_name.get(spec.name) or ExtractedField(spec.name, None, spec.unit, 0.0)
        value = found.value
        if value is not None and spec.type == "number":
            value = _to_number(value)
        elif value is not None and spec.type == "date":
            value = _to_iso_date(value)
        confidence = max(0.0, min(1.0, found.confidence)) if value is not None else 0.0
        fields.append(ExtractedField(spec.name, value, spec.unit or found.unit, round(confidence, 2)))
    result.fields = fields
    result.type_confidence = round(max(0.0, min(1.0, result.type_confidence)), 2)
    return result
