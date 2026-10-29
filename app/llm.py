"""Optional second opinion from a local LLM (Ollama).

The model is only consulted for fields the rules could not extract with enough
confidence, and every answer is *grounded*: a value is accepted only if it can be
found in the document text (and, for the NIT, if its check digit is valid).
This keeps the model useful for messy layouts without letting it invent data.
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from . import nit
from .config import settings
from .models import FieldResult
from .rules import parse_amount, parse_date

log = logging.getLogger(__name__)

FIELD_HINTS = {
    "tax_id": "issuer NIT with verification digit, format 900123456-7",
    "supplier_name": "legal name of the company that ISSUED the invoice",
    "invoice_number": "invoice number including prefix, e.g. FE-1234",
    "issue_date": "issue date, ISO format YYYY-MM-DD",
    "due_date": "due date, ISO format YYYY-MM-DD",
    "total_amount": "total amount to pay, plain number with dot decimals",
}

LLM_CONFIDENCE = 0.65


def build_prompt(text: str, fields: list[str], exclude_tax_ids: set[str]) -> str:
    wanted = "\n".join(f'- "{f}": {FIELD_HINTS[f]}' for f in fields)
    excluded = ", ".join(sorted(exclude_tax_ids)) or "none"
    return (
        "You extract data from a supplier invoice. Answer ONLY with a JSON object.\n"
        f"Keys to return:\n{wanted}\n"
        "Use null when a value is not explicitly written in the document. Never guess.\n"
        f"These NITs belong to the BUYER and must not be returned as tax_id: {excluded}\n\n"
        f'DOCUMENT:\n"""\n{text[:6000]}\n"""'
    )


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def ground(field: str, value: object, text: str, exclude_tax_ids: set[str]) -> str | None:
    """Return a normalised value only if it is supported by the document text."""
    if value in (None, "", "null"):
        return None
    raw = str(value).strip()
    flat_digits = _digits(text)
    lowered = text.lower()

    if field == "tax_id":
        normalized = nit.normalize(raw)
        if not normalized or normalized in exclude_tax_ids:
            return None
        return normalized if _digits(normalized.split("-")[0]) in flat_digits else None
    if field in ("issue_date", "due_date"):
        parsed = parse_date(raw)
        if not parsed:
            return None
        day_month = (f"{parsed.day:02d}", f"{parsed.month:02d}")
        return parsed.isoformat() if str(parsed.year) in text and any(p in text for p in day_month) else None
    if field == "total_amount":
        amount = parse_amount(raw)
        if amount is None:
            return None
        return f"{amount:.2f}" if _digits(str(int(amount))) in flat_digits else None
    if field == "invoice_number":
        # The full alphanumeric token (prefix + number) must appear, not just its digits.
        compact = re.sub(r"[^A-Z0-9]", "", raw.upper())
        flat_text = re.sub(r"[^A-Z0-9]", "", text.upper())
        return raw.upper() if len(_digits(compact)) >= 2 and compact in flat_text else None
    if field == "supplier_name":
        return raw if raw.lower() in lowered else None
    return None


def ask(text: str, fields: list[str], exclude_tax_ids: set[str] | None = None) -> dict[str, FieldResult]:
    """Query Ollama for ``fields``. Returns only grounded answers; never raises."""
    exclude = exclude_tax_ids or set()
    if not settings.ollama_url or not fields:
        return {}
    try:
        response = httpx.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": build_prompt(text, fields, exclude),
                "format": "json",
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=settings.ollama_timeout_s,
        )
        response.raise_for_status()
        payload = json.loads(response.json().get("response") or "{}")
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        log.warning("LLM fallback unavailable: %s", exc)
        return {}

    results: dict[str, FieldResult] = {}
    for field in fields:
        value = ground(field, payload.get(field), text, exclude)
        if value:
            results[field] = FieldResult(value=value, confidence=LLM_CONFIDENCE, source="llm")
    return results
