"""Exercise number ranges per paragraph — all textbooks.

Each textbook has either:
  - static JSON in data/exercise_ranges/{key}.json
  - toc_number mode (exercise range encoded in TOC ``number`` field, e.g. "19-20")
  - makarychev7 built-in table
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.pipeline.makarychev7_exercise_ranges import (
    MAKARYCHEV7_EXERCISE_RANGES,
    MAKARYCHEV7_PAGE_END_OVERRIDE,
)

_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "exercise_ranges"

# textbook_id → config key / mode
_TEXTBOOK_CONFIG: dict[str, dict[str, Any]] = {
    "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f": {"source": "makarychev7"},
    "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8": {"source": "theme_stream"},
    "184640af-64e7-47af-a974-8b8112e6ffb2": {"source": "json", "file": "g5_vilenkin.json"},
    "351a95c1-5208-4ae9-8323-6d7dd5e8bb82": {"source": "json", "file": "g6_vilenkin.json"},
    "5630a994-061d-4c20-9863-fe049c8059fb": {"source": "json", "file": "g5_idum_ch1.json"},
    "47167115-5961-4405-bb55-1bda8ce1b687": {"source": "json", "file": "g5_idum_ch2.json"},
    "4b19752a-3d54-4538-b6a6-26ce1fbb48fd": {"source": "json", "file": "g7_algebra.json"},
    "e8f3a1b2-7c4d-5e6f-8091-2345678abcde": {"source": "theme_stream"},
}


def parse_exercise_num(raw: str) -> int | None:
    """Leading integer from exercise_number (handles '14', '14а', '1.15')."""
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d+)", s)
    if m:
        return int(m.group(1))
    m = re.match(r"^(\d+)\.(\d+)", s)
    if m:
        return int(m.group(2))
    return None


def parse_paragraph_key(raw: str | int) -> str:
    """Normalize TOC paragraph number for lookup ('§ 1' → '1', '§1' → '1')."""
    if raw is None:
        return ""
    s = str(raw).strip()
    s = re.sub(r"^§\s*", "", s, flags=re.I).strip()
    return s


def _range_from_toc_number(number: str) -> tuple[int, int] | None:
    """Parse '1-2', '19–20', '92' → (lo, hi)."""
    s = number.strip().replace("–", "-").replace("—", "-")
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo, hi) if lo <= hi else (hi, lo)
    m = re.match(r"^(\d+)$", s)
    if m:
        n = int(m.group(1))
        return n, n
    return None


@lru_cache(maxsize=32)
def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ranges": {}, "page_end_override": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _json_ranges(textbook_id: str) -> dict[str, tuple[int, int]]:
    cfg = _TEXTBOOK_CONFIG.get(textbook_id, {})
    fname = cfg.get("file")
    if not fname:
        return {}
    data = _load_json(_DATA_DIR / fname)
    out: dict[str, tuple[int, int]] = {}
    for key, val in (data.get("ranges") or {}).items():
        if isinstance(val, (list, tuple)) and len(val) == 2:
            out[str(key)] = (int(val[0]), int(val[1]))
    return out


def _json_page_end_override(textbook_id: str) -> dict[str, int]:
    cfg = _TEXTBOOK_CONFIG.get(textbook_id, {})
    fname = cfg.get("file")
    if not fname:
        return {}
    data = _load_json(_DATA_DIR / fname)
    return {str(k): int(v) for k, v in (data.get("page_end_override") or {}).items()}


def has_ranges(textbook_id: str) -> bool:
    return textbook_id in _TEXTBOOK_CONFIG


def get_ranges(textbook_id: str) -> dict[str, tuple[int, int]]:
    cfg = _TEXTBOOK_CONFIG.get(textbook_id)
    if not cfg:
        return {}
    if cfg["source"] == "makarychev7":
        return {str(k): v for k, v in MAKARYCHEV7_EXERCISE_RANGES.items()}
    if cfg["source"] == "json":
        return _json_ranges(textbook_id)
    return {}


def exercise_range(
    textbook_id: str,
    paragraph_number: str | int,
) -> tuple[int, int] | None:
    cfg = _TEXTBOOK_CONFIG.get(textbook_id)
    if not cfg:
        return None

    key = parse_paragraph_key(paragraph_number)

    if cfg["source"] == "toc_number":
        return _range_from_toc_number(key)

    if cfg["source"] == "theme_stream":
        return None  # boundaries from text headers, not exercise ranges

    if cfg["source"] == "makarychev7":
        try:
            n = int(key)
        except ValueError:
            return None
        return MAKARYCHEV7_EXERCISE_RANGES.get(n)

    if cfg["source"] == "json":
        ranges = _json_ranges(textbook_id)
        if key in ranges:
            return ranges[key]
        try:
            return ranges.get(str(int(key)))
        except ValueError:
            return None

    return None


def page_end_override(textbook_id: str, paragraph_number: str | int) -> int | None:
    cfg = _TEXTBOOK_CONFIG.get(textbook_id)
    if not cfg:
        return None
    key = parse_paragraph_key(paragraph_number)
    if cfg["source"] == "makarychev7":
        try:
            return MAKARYCHEV7_PAGE_END_OVERRIDE.get(int(key))
        except ValueError:
            return None
    if cfg["source"] == "json":
        return _json_page_end_override(textbook_id).get(key)
    return None


def expected_count(textbook_id: str, paragraph_number: str | int) -> int | None:
    r = exercise_range(textbook_id, paragraph_number)
    if not r:
        return None
    lo, hi = r
    return hi - lo + 1


# Per-textbook task ID prefix — avoids G7_TB_{para}_{ex} collisions across books.
_TASK_ID_PREFIX: dict[str, str] = {
    "4b19752a-3d54-4538-b6a6-26ce1fbb48fd": "G7_ALG",  # Алгебра 7 класс (UZ)
    "e8f3a1b2-7c4d-5e6f-8091-2345678abcde": "G8_ALG",  # Алгебра 8 класс (UZ)
}


def task_id_prefix(textbook_id: str, class_level: int) -> str:
    """Stable prefix for tasks_master.id (VARCHAR 60)."""
    if textbook_id in _TASK_ID_PREFIX:
        return _TASK_ID_PREFIX[textbook_id]
    return f"G{class_level}_TB"
