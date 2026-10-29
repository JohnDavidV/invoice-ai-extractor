import pytest

from app import nit


@pytest.mark.parametrize(
    "base, dv",
    [
        ("800197268", 4),  # DIAN's own published NIT
        ("899999034", 1),
        ("860034313", 7),
        ("901555333", nit.check_digit("901555333")),
    ],
)
def test_check_digit(base, dv):
    assert nit.check_digit(base) == dv


def test_normalize_accepts_dots_and_spaces():
    assert nit.normalize("800.197.268-4") == "800197268-4"
    assert nit.normalize(" 800 197 268 - 4 ") == "800197268-4"


def test_normalize_rejects_wrong_check_digit():
    assert nit.normalize("800.197.268-5") is None


def test_normalize_rejects_garbage():
    assert nit.normalize("hello") is None
    assert nit.normalize("") is None
    assert nit.normalize("12-3") is None


def test_format_nit_round_trip():
    full = nit.format_nit("900123456")
    assert nit.normalize(full) == full
