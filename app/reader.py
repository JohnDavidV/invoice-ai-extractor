"""Turn an uploaded document (PDF or image) into plain text.

Strategy:
1. PDFs with a text layer -> read it directly (fast and exact).
2. Scanned PDFs / images -> OCR with Tesseract at 300 DPI.
"""

from __future__ import annotations

import glob
import io
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Literal

from .config import settings

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class ReadResult:
    text: str
    source: Literal["native", "ocr", "none"]
    pages: int = 0
    error: str | None = None


def _configure_tesseract() -> bool:
    """Locate the tesseract binary. Returns False when OCR is unavailable.

    Windows services often run with a PATH different from the interactive user's,
    so an explicit path (env var) wins, then PATH, then the usual install folders.
    """
    try:
        import pytesseract
    except ImportError:
        return False

    if settings.tesseract_cmd and os.path.isfile(settings.tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        return True
    if shutil.which("tesseract"):
        return True
    for candidate in glob.glob(r"C:\Program Files*\Tesseract-OCR\tesseract.exe"):
        pytesseract.pytesseract.tesseract_cmd = candidate
        return True
    return False


OCR_AVAILABLE = _configure_tesseract()


def _ocr_image(image) -> str:
    import pytesseract

    try:
        return pytesseract.image_to_string(image, lang=settings.ocr_lang)
    except pytesseract.TesseractError:
        # Language pack missing: fall back to the default language instead of failing.
        return pytesseract.image_to_string(image)


def read_pdf(data: bytes) -> ReadResult:
    import pymupdf as fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # corrupt / encrypted / not a PDF
        return ReadResult("", "none", error=f"invalid_pdf: {exc}")

    with doc:
        native = "\n".join(page.get_text("text") for page in doc)
        if len(native.strip()) >= settings.min_native_chars:
            return ReadResult(native, "native", pages=doc.page_count)

        if not OCR_AVAILABLE:
            return ReadResult(native, "none", pages=doc.page_count, error="ocr_unavailable")

        from PIL import Image

        chunks = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            chunks.append(_ocr_image(image))
        return ReadResult("\n".join(chunks), "ocr", pages=doc.page_count)


def read_image(data: bytes) -> ReadResult:
    if not OCR_AVAILABLE:
        return ReadResult("", "none", error="ocr_unavailable")
    from PIL import Image

    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:
        return ReadResult("", "none", error=f"invalid_image: {exc}")
    return ReadResult(_ocr_image(image), "ocr", pages=1)


def read_document(data: bytes, filename: str) -> ReadResult:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".pdf" or data[:5] == b"%PDF-":
        return read_pdf(data)
    if ext in IMAGE_EXTENSIONS:
        return read_image(data)
    return ReadResult("", "none", error=f"unsupported_type: {ext or 'unknown'}")
