"""Colombian tax ID (NIT) helpers.

A NIT is a 6-15 digit number followed by a verification digit (DV) computed with
the DIAN modulo-11 algorithm. Validating the DV is the single most effective way
to tell a real NIT apart from any other long number printed on an invoice
(phone numbers, account numbers, invoice numbers...).
"""

from __future__ import annotations

import re

# DIAN weights, applied from the right-most digit of the base number.
_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def check_digit(base: str) -> int:
    """Return the DIAN verification digit for a NIT base number (digits only)."""
    digits = re.sub(r"\D", "", base)
    if not digits:
        raise ValueError("NIT base must contain digits")
    if len(digits) > len(_WEIGHTS):
        raise ValueError("NIT base is too long")
    total = sum(int(d) * w for d, w in zip(reversed(digits), _WEIGHTS, strict=False))
    remainder = total % 11
    return remainder if remainder in (0, 1) else 11 - remainder


def is_valid(base: str, dv: int | str) -> bool:
    """True when ``dv`` is the correct verification digit for ``base``."""
    try:
        return check_digit(base) == int(dv)
    except (ValueError, TypeError):
        return False


def normalize(raw: str) -> str | None:
    """Normalise ``'900.123.456-7'`` style strings to ``'900123456-7'``.

    Returns ``None`` when the input does not look like ``base-dv`` or when the
    verification digit does not match.
    """
    match = re.fullmatch(r"\s*([\d.,\s]{6,20})\s*[-–]\s*(\d)\s*", raw or "")
    if not match:
        return None
    base = re.sub(r"\D", "", match.group(1))
    dv = match.group(2)
    if not 6 <= len(base) <= 15 or not is_valid(base, dv):
        return None
    return f"{base}-{dv}"


def format_nit(base: str) -> str:
    """Build a full ``base-dv`` NIT from a base number."""
    digits = re.sub(r"\D", "", base)
    return f"{digits}-{check_digit(digits)}"
