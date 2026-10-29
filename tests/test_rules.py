from datetime import date
from decimal import Decimal

import pytest

from app import rules
from app.nit import format_nit

SUPPLIER_NIT = format_nit("900123456")
BUYER_NIT = format_nit("901555333")

INVOICE = f"""
FERRETERIA LOS ANDES S.A.S.
NIT: {SUPPLIER_NIT}
Tel 604 444 1234
FACTURA ELECTRONICA DE VENTA No. FE-4521
Fecha de emision: 15/03/2026
Fecha de vencimiento: 14/04/2026
CLIENTE: ACME S.A.S. NIT {BUYER_NIT}
Subtotal: $ 1.000.000,00
IVA 19%: $ 190.000,00
TOTAL A PAGAR: $ 1.190.000,00
"""


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("15/03/2026", date(2026, 3, 15)),
        ("2026-03-15", date(2026, 3, 15)),
        ("15 de marzo de 2026", date(2026, 3, 15)),
        ("15 MARZO 2026", date(2026, 3, 15)),
        ("March 15, 2026", date(2026, 3, 15)),
        ("31/02/2026", None),
        ("no date here", None),
    ],
)
def test_parse_date(raw, expected):
    assert rules.parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("$ 1.190.000,00", Decimal("1190000.00")),
        ("1,190,000.00", Decimal("1190000.00")),
        ("$1.190.000", Decimal("1190000")),
        ("2.500,5", Decimal("2500.5")),
        ("abc", None),
    ],
)
def test_parse_amount(raw, expected):
    assert rules.parse_amount(raw) == expected


def test_full_invoice():
    fields = rules.extract_all(INVOICE, exclude_tax_ids={BUYER_NIT})
    assert fields["tax_id"].value == SUPPLIER_NIT
    assert fields["tax_id"].confidence >= 0.9
    assert fields["supplier_name"].value == "FERRETERIA LOS ANDES S.A.S."
    assert fields["invoice_number"].value == "FE-4521"
    assert fields["issue_date"].value == "2026-03-15"
    assert fields["due_date"].value == "2026-04-14"
    assert fields["total_amount"].value == "1190000.00"


def test_buyer_nit_is_never_returned():
    text = f"Cliente NIT {BUYER_NIT}"
    assert rules.extract_tax_id(text, exclude={BUYER_NIT}).value is None


def test_phone_numbers_are_not_nits():
    assert rules.extract_tax_id("Tel 604-444-1234 cel 300 123 4567-8").value is None


def test_ambiguous_nits_lower_confidence():
    other = format_nit("830987654")
    text = f"NIT {SUPPLIER_NIT}\nNIT {other}"
    result = rules.extract_tax_id(text)
    assert result.value in {SUPPLIER_NIT, other}
    assert result.confidence < 0.75


def test_subtotal_is_not_the_total():
    assert rules.extract_total("Subtotal $ 900.000\nTotal $ 1.071.000").value == "1071000.00"


def test_due_before_issue_is_flagged():
    _, due = rules.extract_dates("Fecha de emision: 10/05/2026\nFecha de vencimiento: 01/05/2026")
    assert due.confidence < 0.5
