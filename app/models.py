from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["rules", "llm", "none"]


class FieldResult(BaseModel):
    value: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    source: Source = "none"


class ExtractionResult(BaseModel):
    readable: bool
    reason: str | None = None
    text_source: Literal["native", "ocr", "none"] = "none"
    tax_id: FieldResult = FieldResult()
    supplier_name: FieldResult = FieldResult()
    invoice_number: FieldResult = FieldResult()
    issue_date: FieldResult = FieldResult()
    due_date: FieldResult = FieldResult()
    total_amount: FieldResult = FieldResult()
    overall_confidence: float = 0.0

    def as_flat_dict(self) -> dict[str, str | None]:
        return {
            "tax_id": self.tax_id.value,
            "supplier_name": self.supplier_name.value,
            "invoice_number": self.invoice_number.value,
            "issue_date": self.issue_date.value,
            "due_date": self.due_date.value,
            "total_amount": self.total_amount.value,
        }


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
