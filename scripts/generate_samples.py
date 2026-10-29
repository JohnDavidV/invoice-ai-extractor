"""Generate a synthetic, 100% fictional invoice dataset with ground truth.

    python scripts/generate_samples.py --count 30 --out samples

Three different layouts are produced, and a share of the documents is rasterised
into image-only PDFs to exercise the OCR path. Every company, NIT and amount is
random - no real data is ever stored in this repository.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pymupdf as fitz
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.nit import format_nit  # noqa: E402

BUYER_NIT = format_nit("901555333")
BUYER = "ACME SERVICIOS DE PRUEBA S.A.S."

NAMES = [
    "Andes",
    "Caribe",
    "Pacifico",
    "Sabana",
    "Cordillera",
    "Llanos",
    "Montaña",
    "Rio Claro",
    "Altiplano",
    "Meridiano",
]
TRADES = [
    "Suministros",
    "Tecnologia",
    "Ferreteria",
    "Logistica",
    "Papeleria",
    "Mantenimiento",
    "Alimentos",
    "Seguridad Industrial",
]
SUFFIXES = ["S.A.S.", "S.A.", "LTDA", "S.A.S"]
MONTHS_ES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def money_es(value: float) -> str:
    whole, cents = f"{value:,.2f}".split(".")
    return "$ " + whole.replace(",", ".") + "," + cents


def random_invoice(rng: random.Random, i: int) -> dict:
    issue = date(2026, 1, 1) + timedelta(days=rng.randint(0, 280))
    items = [
        (
            rng.choice(["Servicio tecnico", "Repuestos", "Insumos", "Licencia anual", "Transporte"]),
            rng.randint(1, 12),
            rng.randint(20, 900) * 1000,
        )
        for _ in range(rng.randint(1, 4))
    ]
    subtotal = sum(q * p for _, q, p in items)
    iva = round(subtotal * 0.19, 2)
    return {
        "file": f"invoice_{i:03d}.pdf",
        "supplier_name": f"{rng.choice(TRADES)} {rng.choice(NAMES)} {rng.choice(SUFFIXES)}",
        "tax_id": format_nit(str(rng.randint(800_000_000, 901_999_999))),
        "invoice_number": f"{rng.choice(['FE', 'FV', 'SETP'])}{rng.choice(['', '-'])}{rng.randint(100, 99999)}",
        "issue_date": issue.isoformat(),
        "due_date": (issue + timedelta(days=rng.choice([15, 30, 45, 60]))).isoformat(),
        "items": items,
        "subtotal": subtotal,
        "iva": iva,
        "total_amount": f"{subtotal + iva:.2f}",
    }


def dotted(nit_value: str) -> str:
    base, dv = nit_value.split("-")
    return f"{int(base):,}".replace(",", ".") + f"-{dv}"


def draw(inv: dict, layout: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    issue = date.fromisoformat(inv["issue_date"])
    due = date.fromisoformat(inv["due_date"])
    y = h - 60

    def line(text: str, x: float = 50, size: int = 10, bold: bool = False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, text)
        y -= size + 6

    if layout == 0:
        line(inv["supplier_name"], size=16, bold=True)
        line(f"NIT: {dotted(inv['tax_id'])}")
        line("Calle 10 # 20-30, Medellin  Tel: 604 444 1234")
        y -= 10
        line(f"FACTURA ELECTRONICA DE VENTA No. {inv['invoice_number']}", size=12, bold=True)
        line(f"Fecha de emision: {issue.strftime('%d/%m/%Y')}")
        line(f"Fecha de vencimiento: {due.strftime('%d/%m/%Y')}")
    elif layout == 1:
        line(f"Factura N° {inv['invoice_number']}", x=380, size=12, bold=True)
        line(inv["supplier_name"], size=14, bold=True)
        line(f"NIT {inv['tax_id']}  - Regimen comun")
        line(f"Fecha de expedicion: {issue.day} de {MONTHS_ES[issue.month - 1]} de {issue.year}")
        line(f"Fecha limite de pago: {due.day} de {MONTHS_ES[due.month - 1]} de {due.year}")
    else:
        line(inv["supplier_name"].upper(), size=15, bold=True)
        line(f"N.I.T. {dotted(inv['tax_id'])}")
        line(f"Invoice / Factura Nro: {inv['invoice_number']}")
        line(f"Fecha factura: {issue.isoformat()}    Vence: {due.isoformat()}")

    y -= 10
    line("CLIENTE", bold=True)
    line(f"{BUYER}  NIT: {dotted(BUYER_NIT)}")
    y -= 10
    line("Descripcion                      Cant.      Valor unitario", bold=True)
    for desc, qty, price in inv["items"]:
        line(f"{desc:<32} {qty:>4}      {money_es(price)}")
    y -= 10
    line(f"Subtotal: {money_es(inv['subtotal'])}", x=330)
    line(f"IVA 19%: {money_es(inv['iva'])}", x=330)
    line(f"TOTAL A PAGAR: {money_es(float(inv['total_amount']))}", x=330, size=12, bold=True)
    c.showPage()
    c.save()
    return buf.getvalue()


def rasterise(pdf_bytes: bytes) -> bytes:
    """Convert to an image-only PDF (simulates a scanned document)."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=200)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("png"))
    return out.tobytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--out", default="samples")
    parser.add_argument("--scanned-ratio", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    truth = []
    for i in range(1, args.count + 1):
        inv = random_invoice(rng, i)
        pdf = draw(inv, layout=i % 3)
        scanned = rng.random() < args.scanned_ratio
        (out / inv["file"]).write_bytes(rasterise(pdf) if scanned else pdf)
        truth.append(
            {k: inv[k] for k in ("file", "tax_id", "supplier_name", "invoice_number", "issue_date", "due_date", "total_amount")}
            | {"scanned": scanned}
        )
    (out / "ground_truth.json").write_text(json.dumps({"buyer_tax_id": BUYER_NIT, "invoices": truth}, indent=2))
    print(f"Generated {len(truth)} invoices in {out}/")


if __name__ == "__main__":
    main()
