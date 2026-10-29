"""Measure field-level accuracy against a labelled dataset.

    python scripts/evaluate.py samples

Prints a per-field accuracy table and the documents that failed, so every rule
change can be checked for regressions before it reaches production.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline import extract  # noqa: E402

FIELDS = ["tax_id", "supplier_name", "invoice_number", "issue_date", "due_date", "total_amount"]


def normalise(field: str, value: str | None) -> str:
    if value is None:
        return ""
    value = value.strip()
    if field == "supplier_name":
        # OCR may drop accents (Ñ -> N): compare without diacritics.
        value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
        return " ".join(value.upper().replace(".", "").split())
    if field == "invoice_number":
        return value.upper().replace("-", "")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", nargs="?", default="samples")
    parser.add_argument("--min-accuracy", type=float, default=0.0, help="Exit 1 if overall accuracy is below this")
    args = parser.parse_args()

    root = Path(args.dataset)
    truth = json.loads((root / "ground_truth.json").read_text())
    exclude = {truth["buyer_tax_id"]}
    hits, failures = Counter(), []

    for item in truth["invoices"]:
        result = extract((root / item["file"]).read_bytes(), item["file"], exclude).as_flat_dict()
        for field in FIELDS:
            if normalise(field, result[field]) == normalise(field, item[field]):
                hits[field] += 1
            else:
                failures.append((item["file"], field, item[field], result[field]))

    total = len(truth["invoices"])
    print(f"\n{'field':<16}{'accuracy':>10}")
    print("-" * 26)
    for field in FIELDS:
        print(f"{field:<16}{hits[field] / total:>10.1%}")
    overall = sum(hits.values()) / (total * len(FIELDS))
    print("-" * 26)
    print(f"{'overall':<16}{overall:>10.1%}  ({total} documents)\n")
    for file, field, expected, got in failures[:20]:
        print(f"  MISS {file:<18} {field:<15} expected={expected!r} got={got!r}")
    return 0 if overall >= args.min_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
