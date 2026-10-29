"""Extraction pipeline: read -> rules -> (optional) grounded LLM -> score."""

from __future__ import annotations

from . import llm, rules
from .config import settings
from .models import ExtractionResult
from .reader import read_document

# Fields that matter most for routing the document (weights for overall confidence).
WEIGHTS = {
    "tax_id": 0.35,
    "invoice_number": 0.2,
    "issue_date": 0.15,
    "total_amount": 0.15,
    "supplier_name": 0.1,
    "due_date": 0.05,
}


def extract_from_text(text: str, exclude_tax_ids: set[str] | None = None) -> dict:
    fields = rules.extract_all(text, exclude_tax_ids)
    weak = [name for name, result in fields.items() if result.confidence < settings.min_confidence]
    for name, result in llm.ask(text, weak, exclude_tax_ids).items():
        if result.confidence > fields[name].confidence:
            fields[name] = result
    return fields


def extract(data: bytes, filename: str, exclude_tax_ids: set[str] | None = None) -> ExtractionResult:
    read = read_document(data, filename)
    if read.error and not read.text.strip():
        return ExtractionResult(readable=False, reason=read.error, text_source=read.source)
    if len(read.text.strip()) < 20:
        return ExtractionResult(readable=False, reason="no_text_found", text_source=read.source)

    fields = extract_from_text(read.text, exclude_tax_ids)
    overall = sum(WEIGHTS[name] * result.confidence for name, result in fields.items())
    return ExtractionResult(
        readable=True,
        text_source=read.source,
        overall_confidence=round(overall, 2),
        **fields,
    )
