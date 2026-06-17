"""Per-textbook digitization pipeline mode."""
from __future__ import annotations

# page       — default: TOC page ranges, optional exercise-range filter
# theme_stream — sequential OCR; theme headers switch active TOC § (g6 local)
TEXTBOOK_PIPELINE_MODE: dict[str, str] = {
    "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8": "theme_stream",  # G6 местный
    "e8f3a1b2-7c4d-5e6f-8091-2345678abcde": "theme_stream",  # G8 IDUM — сквозная нумерация
}


def pipeline_mode(textbook_id: str) -> str:
    return TEXTBOOK_PIPELINE_MODE.get(textbook_id, "page")
