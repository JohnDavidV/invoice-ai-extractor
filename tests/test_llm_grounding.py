"""The LLM fallback must never introduce values that are not in the document."""

import json

import httpx
import pytest

from app import llm
from app.nit import format_nit

SUPPLIER = format_nit("900123456")
TEXT = f"Proveedor Ejemplo SAS  NIT {SUPPLIER}  Factura 7788  Fecha 03/02/2026  Total 450.000"


def test_ground_accepts_values_present_in_text():
    assert llm.ground("tax_id", SUPPLIER, TEXT, set()) == SUPPLIER
    assert llm.ground("invoice_number", "7788", TEXT, set()) == "7788"
    assert llm.ground("issue_date", "2026-02-03", TEXT, set()) == "2026-02-03"
    assert llm.ground("total_amount", "450000", TEXT, set()) == "450000.00"
    assert llm.ground("supplier_name", "Proveedor Ejemplo SAS", TEXT, set()) == "Proveedor Ejemplo SAS"


@pytest.mark.parametrize(
    "field, hallucination",
    [
        ("tax_id", format_nit("811222333")),  # valid NIT, not in the text
        ("tax_id", "900123456-0"),  # wrong check digit
        ("invoice_number", "9999"),
        ("issue_date", "2025-12-31"),
        ("total_amount", "999999"),
        ("supplier_name", "Invented Corp"),
    ],
)
def test_ground_rejects_hallucinations(field, hallucination):
    assert llm.ground(field, hallucination, TEXT, set()) is None


def test_ground_rejects_buyer_nit():
    assert llm.ground("tax_id", SUPPLIER, TEXT, {SUPPLIER}) is None


def test_ask_is_noop_without_ollama(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(llm, "settings", replace(llm.settings, ollama_url=""))
    assert llm.ask(TEXT, ["tax_id"]) == {}


def test_ask_uses_ollama_and_filters(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(llm, "settings", replace(llm.settings, ollama_url="http://ollama:11434"))

    def fake_post(url, timeout=None, **_):
        body = {"tax_id": SUPPLIER, "invoice_number": "INVENTED-1"}
        return httpx.Response(200, json={"response": json.dumps(body)}, request=httpx.Request("POST", url))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    result = llm.ask(TEXT, ["tax_id", "invoice_number"])
    assert result["tax_id"].value == SUPPLIER
    assert result["tax_id"].source == "llm"
    assert "invoice_number" not in result


def test_ask_survives_ollama_errors(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(llm, "settings", replace(llm.settings, ollama_url="http://ollama:11434"))

    def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(llm.httpx, "post", boom)
    assert llm.ask(TEXT, ["tax_id"]) == {}
