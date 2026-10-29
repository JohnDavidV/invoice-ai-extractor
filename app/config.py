"""Runtime settings, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Optional local LLM (Ollama). Empty URL = rules only, fully offline.
    ollama_url: str = os.environ.get("EXTRACTOR_OLLAMA_URL", "").rstrip("/")
    ollama_model: str = os.environ.get("EXTRACTOR_OLLAMA_MODEL", "llama3.2:3b")
    ollama_timeout_s: float = float(os.environ.get("EXTRACTOR_OLLAMA_TIMEOUT", "60"))
    # Below this confidence a field is sent to the LLM (if configured).
    min_confidence: float = float(os.environ.get("EXTRACTOR_MIN_CONFIDENCE", "0.55"))
    # If the native PDF text layer has fewer characters than this, OCR is used.
    min_native_chars: int = int(os.environ.get("EXTRACTOR_MIN_NATIVE_CHARS", "40"))
    # Explicit tesseract binary (useful on Windows services where PATH differs).
    tesseract_cmd: str = os.environ.get("EXTRACTOR_TESSERACT_CMD", "")
    ocr_lang: str = os.environ.get("EXTRACTOR_OCR_LANG", "spa+eng")
    max_upload_mb: int = int(os.environ.get("EXTRACTOR_MAX_UPLOAD_MB", "15"))


settings = Settings()
