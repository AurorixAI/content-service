"""OCR quality helpers — shared by ocr.py and orchestrator."""
from __future__ import annotations

MIN_USABLE_OCR_CHARS = 200

_OCR_ERROR_MARKERS = (
    "[ошибка ocr",
    "ошибка ocr исходного",
    "[пустая страница]",
)


def is_usable_ocr_text(text: str) -> bool:
    """False for empty, too short, or error-placeholder OCR."""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) < MIN_USABLE_OCR_CHARS:
        return False
    lower = stripped.lower()
    if any(marker in lower for marker in _OCR_ERROR_MARKERS):
        # Allow if substantial real content exists beyond error lines
        lines = [ln for ln in stripped.splitlines() if ln.strip()]
        good = [
            ln for ln in lines
            if not any(m in ln.lower() for m in _OCR_ERROR_MARKERS)
        ]
        if len("\n".join(good).strip()) < MIN_USABLE_OCR_CHARS:
            return False
    return True
