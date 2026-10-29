"""HTTP API.

GET  /health   -> {"status": "ok", "ocr": bool, "llm": bool}
POST /extract  -> multipart file upload, returns ExtractionResult
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from . import __version__
from .config import settings
from .models import ExtractionResult
from .pipeline import extract
from .reader import OCR_AVAILABLE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Invoice AI Extractor",
    version=__version__,
    description="Extracts NIT, supplier, invoice number, dates and totals from supplier invoices.",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ocr": OCR_AVAILABLE, "llm": bool(settings.ollama_url)}


@app.post("/extract", response_model=ExtractionResult)
async def extract_endpoint(
    file: UploadFile = File(...),
    exclude_tax_ids: str = Form("", description="Comma separated NITs to ignore (the buyer's own NIT)"),
) -> ExtractionResult:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File larger than {settings.max_upload_mb} MB")
    excluded = {x.strip() for x in exclude_tax_ids.split(",") if x.strip()}
    return extract(data, file.filename or "upload", excluded)
