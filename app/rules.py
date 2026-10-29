"""Deterministic, explainable extraction rules.

Every extractor returns a ``FieldResult`` with a confidence score so the pipeline
can decide which fields are good enough and which ones deserve a second opinion
from the local LLM. Rules always run first: they are fast, free, auditable and
never hallucinate.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from . import nit
from .models import FieldResult

# --------------------------------------------------------------------------- helpers

MONTHS = {
    "ene": 1,
    "enero": 1,
    "jan": 1,
    "january": 1,
    "feb": 2,
    "febrero": 2,
    "february": 2,
    "mar": 3,
    "marzo": 3,
    "march": 3,
    "abr": 4,
    "abril": 4,
    "apr": 4,
    "april": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "june": 6,
    "jul": 7,
    "julio": 7,
    "july": 7,
    "ago": 8,
    "agosto": 8,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "septiembre": 9,
    "setiembre": 9,
    "september": 9,
    "oct": 10,
    "octubre": 10,
    "october": 10,
    "nov": 11,
    "noviembre": 11,
    "november": 11,
    "dic": 12,
    "diciembre": 12,
    "dec": 12,
    "december": 12,
}

COMPANY_SUFFIX = re.compile(
    r"\b(S\.?\s?A\.?\s?S\.?|S\.?\s?A\.?|LTDA\.?|E\.?\s?U\.?|S\.?\s?C\.?\s?A\.?|INC\.?|LLC|CORP\.?)\s*$",
    re.IGNORECASE,
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        if y < 100:
            y += 2000
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(raw: str) -> date | None:
    """Parse the date formats seen on Colombian invoices (day-first by default)."""
    s = strip_accents(raw.lower()).strip()

    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", s)  # 2026-03-15
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", s)  # 15/03/2026
    if m:
        return _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    m = re.search(r"\b(\d{1,2})\s*(?:de\s+)?([a-z]{3,10})\.?\s*(?:de\s+|del\s+)?(\d{4})\b", s)  # 15 de marzo de 2026
    if m and m.group(2) in MONTHS:
        return _safe_date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))

    m = re.search(r"\b([a-z]{3,10})\.?\s+(\d{1,2}),?\s+(\d{4})\b", s)  # March 15, 2026
    if m and m.group(1) in MONTHS:
        return _safe_date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return None


def parse_amount(raw: str) -> Decimal | None:
    """Parse ``$ 1.234.567,89`` (es-CO) and ``1,234,567.89`` (en-US) amounts."""
    s = re.sub(r"[^\d.,]", "", raw)
    if not s or not any(c.isdigit() for c in s):
        return None
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot > -1 and last_comma > -1:
        decimal_sep = "." if last_dot > last_comma else ","
    elif last_comma > -1:
        # "1.234,5" handled above; here only commas: decimal if 1-2 digits follow the last one
        decimal_sep = "," if len(s) - last_comma - 1 in (1, 2) else None
    elif last_dot > -1:
        decimal_sep = "." if len(s) - last_dot - 1 in (1, 2) else None
    else:
        decimal_sep = None

    if decimal_sep:
        integer, _, fraction = s.rpartition(decimal_sep)
        integer = re.sub(r"[.,]", "", integer)
        s = f"{integer}.{fraction}"
    else:
        s = re.sub(r"[.,]", "", s)
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


# --------------------------------------------------------------------------- tax id

_NIT_CANDIDATE = re.compile(r"(?<![\d.])(\d{1,3}(?:[.,\s]?\d{3}){1,4})\s*[-–]\s*(\d)(?!\d)")
_NIT_LABEL = re.compile(r"\b(nit|n\.i\.t|rut|tax\s*id)\b", re.IGNORECASE)


def extract_tax_id(text: str, exclude: set[str] | None = None) -> FieldResult:
    """Find the issuer's NIT.

    ``exclude`` holds NITs that must never be returned - typically the buyer's
    own NIT, which is printed on every invoice it receives.
    """
    exclude = {nit.normalize(e) or e for e in (exclude or set())}
    head_limit = max(len(text) * 0.4, 400)
    scored: dict[str, float] = {}

    for match in _NIT_CANDIDATE.finditer(text):
        normalized = nit.normalize(f"{match.group(1)}-{match.group(2)}")
        if not normalized or normalized in exclude:
            continue
        score = 0.70
        window = text[max(0, match.start() - 25) : match.start()]
        if _NIT_LABEL.search(window):
            score += 0.20
        if match.start() <= head_limit:
            score += 0.05
        scored[normalized] = max(scored.get(normalized, 0), score)

    if not scored:
        return FieldResult()
    ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
    best, score = ranked[0]
    if len(ranked) > 1 and ranked[1][1] >= score - 0.05:
        score -= 0.25  # two plausible issuers: ambiguous, ask for a second opinion
    return FieldResult(value=best, confidence=round(min(score, 0.99), 2), source="rules")


# --------------------------------------------------------------------------- invoice number

_INVOICE_NUMBER = re.compile(
    r"(?:factura(?:\s+electr[oó]nica)?(?:\s+de\s+venta)?|invoice|fe|fv)\s*"
    r"(?:n[oº°]\.?|nro\.?|n[uú]m(?:ero)?\.?|#|no\.)?\s*[:#]?\s*"
    r"([A-Z]{0,6}[-\s]?\d{2,12})\b",
    re.IGNORECASE,
)


def extract_invoice_number(text: str) -> FieldResult:
    for match in _INVOICE_NUMBER.finditer(text):
        value = re.sub(r"\s+", "", match.group(1)).upper()
        if len(re.sub(r"\D", "", value)) < 2:
            continue
        labelled = bool(re.search(r"(n[oº°]|nro|n[uú]m|#)", match.group(0), re.IGNORECASE))
        return FieldResult(value=value, confidence=0.9 if labelled else 0.7, source="rules")
    return FieldResult()


# --------------------------------------------------------------------------- dates

_ISSUE_LABEL = re.compile(r"fecha\s*(?:de\s*)?(?:emisi[oó]n|expedici[oó]n|factura|generaci[oó]n)|issue\s*date|fecha\s*:", re.IGNORECASE)
_DUE_LABEL = re.compile(r"fecha\s*(?:de\s*)?(?:vencimiento|pago|l[ií]mite)|vence|due\s*date", re.IGNORECASE)


def _date_after_label(text: str, label: re.Pattern) -> date | None:
    for match in label.finditer(text):
        found = parse_date(text[match.end() : match.end() + 40])
        if found:
            return found
    return None


def extract_dates(text: str) -> tuple[FieldResult, FieldResult]:
    issue = _date_after_label(text, _ISSUE_LABEL)
    due = _date_after_label(text, _DUE_LABEL)
    issue_result = FieldResult(value=issue.isoformat(), confidence=0.9, source="rules") if issue else FieldResult()
    if not issue:
        # Fallback: first date anywhere in the document, low confidence.
        for line in _lines(text):
            first = parse_date(line)
            if first:
                issue_result = FieldResult(value=first.isoformat(), confidence=0.5, source="rules")
                break
    due_result = FieldResult(value=due.isoformat(), confidence=0.9, source="rules") if due else FieldResult()
    if issue and due and due < issue:
        due_result.confidence = 0.4  # inconsistent: due before issue
    return issue_result, due_result


# --------------------------------------------------------------------------- total amount

_TOTAL_LABEL = re.compile(r"(total\s*a\s*pagar|valor\s*total|total\s*factura|gran\s*total|total\s*due|total)\b", re.IGNORECASE)
_AMOUNT = re.compile(r"\$?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\$?\s*\d+(?:[.,]\d{1,2})?")


def extract_total(text: str) -> FieldResult:
    best: tuple[int, Decimal] | None = None
    for match in _TOTAL_LABEL.finditer(text):
        label = match.group(1).lower()
        if re.search(r"sub\s*$", text[max(0, match.start() - 4) : match.start()], re.IGNORECASE):
            continue  # "Subtotal"
        tail = text[match.end() : match.end() + 40]
        amount_match = _AMOUNT.search(tail)
        if not amount_match:
            continue
        amount = parse_amount(amount_match.group(0))
        if amount is None or amount <= 0:
            continue
        priority = 2 if ("pagar" in label or "factura" in label or "gran" in label or "due" in label) else 1
        if best is None or priority > best[0] or (priority == best[0] and amount > best[1]):
            best = (priority, amount)
    if not best:
        return FieldResult()
    return FieldResult(value=f"{best[1]:.2f}", confidence=0.9 if best[0] == 2 else 0.7, source="rules")


# --------------------------------------------------------------------------- supplier


def extract_supplier(text: str, tax_id: str | None = None) -> FieldResult:
    lines = _lines(text)[:25]
    for line in lines:
        if COMPANY_SUFFIX.search(line) and len(line) <= 90 and not _NIT_LABEL.search(line):
            return FieldResult(value=re.sub(r"\s{2,}", " ", line), confidence=0.85, source="rules")
    if tax_id:
        base = tax_id.split("-")[0]
        for i, line in enumerate(lines):
            if base in re.sub(r"\D", "", line) and i > 0:
                return FieldResult(value=lines[i - 1], confidence=0.5, source="rules")
    return FieldResult()


# --------------------------------------------------------------------------- entry point


def extract_all(text: str, exclude_tax_ids: set[str] | None = None) -> dict[str, FieldResult]:
    tax_id = extract_tax_id(text, exclude_tax_ids)
    issue, due = extract_dates(text)
    return {
        "tax_id": tax_id,
        "supplier_name": extract_supplier(text, tax_id.value),
        "invoice_number": extract_invoice_number(text),
        "issue_date": issue,
        "due_date": due,
        "total_amount": extract_total(text),
    }
