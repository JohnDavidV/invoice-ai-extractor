import io
import random

import pytest
from fastapi.testclient import TestClient

from app.main import app
from scripts.generate_samples import BUYER_NIT, draw, random_invoice

client = TestClient(app)


@pytest.fixture(scope="module")
def sample():
    invoice = random_invoice(random.Random(7), 1)
    return invoice, draw(invoice, layout=0)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_extract_native_pdf(sample):
    invoice, pdf = sample
    response = client.post(
        "/extract",
        files={"file": ("invoice.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"exclude_tax_ids": BUYER_NIT},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["readable"] is True
    assert body["text_source"] == "native"
    assert body["tax_id"]["value"] == invoice["tax_id"]
    assert body["total_amount"]["value"] == invoice["total_amount"]
    assert body["overall_confidence"] > 0.8


def test_rejects_empty_file():
    response = client.post("/extract", files={"file": ("x.pdf", io.BytesIO(b""), "application/pdf")})
    assert response.status_code == 400


def test_unsupported_type_is_unreadable():
    response = client.post("/extract", files={"file": ("x.docx", io.BytesIO(b"PK\x03\x04"), "application/zip")})
    assert response.status_code == 200
    assert response.json()["readable"] is False
