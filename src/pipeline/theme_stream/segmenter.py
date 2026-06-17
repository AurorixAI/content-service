"""Sequential theme-stream digitization for textbooks with global exercise numbering."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.pipeline.theme_stream.detector import ThemeMarker, find_markers
from src.pipeline.theme_stream.matcher import TocMatcher

log = logging.getLogger(__name__)

_BACK_MATTER_MARKERS = (
    "итоговое повторение",
    "ответы",
    "исторические сведения",
    "mundarija",
    "содержание",
)


@dataclass
class _Segment:
    toc_entry: dict | None = None
    marker: ThemeMarker | None = None
    page_start: int = 0
    page_end: int = 0
    texts: list[str] = field(default_factory=list)
    match_confidence: float = 0.0

    def append(self, page: int, text: str) -> None:
        if not self.page_start:
            self.page_start = page
        self.page_end = page
        if text.strip():
            self.texts.append(text)

    @property
    def combined_text(self) -> str:
        return "\n\n--- страница ---\n\n".join(self.texts)

    def has_content(self) -> bool:
        return bool(self.combined_text.strip())


def _is_back_matter(text: str, page: int, pdf_total: int) -> bool:
    if page >= pdf_total - 12:
        return True
    low = text.lower()
    return any(m in low for m in _BACK_MATTER_MARKERS) and page > 200


def _flush(segments: list[_Segment], current: _Segment) -> _Segment:
    if current.has_content() and current.toc_entry:
        segments.append(current)
    return _Segment()


def build_segments_from_pages(
    pages: list[tuple[int, str]],
    matcher: TocMatcher,
    *,
    default_toc: dict | None = None,
) -> list[_Segment]:
    """Group OCR pages into TOC-aligned segments by detected theme headers."""
    segments: list[_Segment] = []
    current = _Segment(toc_entry=default_toc)

    for page, text in pages:
        if not text.strip():
            continue

        markers = find_markers(text)
        if not markers:
            current.append(page, text)
            continue

        pos = 0
        for mk in markers:
            before = text[pos:mk.offset]
            if before.strip():
                current.append(page, before)

            current = _flush(segments, current)
            matched, conf = matcher.match(mk)
            if not matched:
                log.warning(
                    "theme-stream: unmatched header p.%d %r",
                    page, mk.line[:60],
                )
            current = _Segment(toc_entry=matched, marker=mk, match_confidence=conf)
            pos = mk.offset + len(mk.line)

        tail = text[pos:]
        if tail.strip():
            current.append(page, tail)

    _flush(segments, current)
    return segments
