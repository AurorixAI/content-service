"""Extract exercise number ranges from OCR text of a textbook paragraph.

Works across textbook families (Vilenkin, IDUM, …):
  - global continuous numbering (1…737)
  - local § numbering (1…25) mapped via previous § hi
  - count-only fallback when OCR drops numbers but markers remain
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# ── Section markers (RU math textbooks) ─────────────────────────────────────
_EXERCISE_SECTION = re.compile(
    r"(?:"
    r"упражнения\s+для\s+работы\s+в\s+классе"
    r"|упражнения\s+для\s+домашней\s+работы"
    r"|упражнения\s+для\s+самостоятельной\s+работы"
    r"|^#{1,3}\s*упражнения\b"
    r"|\bупражнения\b"
    r"|задачи\s+для\s+самостоятельного\s+решения"
    r"|задачи\s+для\s+дополнительной\s+работы"
    r")",
    re.I | re.M,
)

# Stop scanning at next major heading after exercises started
_SECTION_STOP = re.compile(
    r"(?:^#{1,2}\s+\d+\.\s+|^#{1,2}\s+[А-ЯA-Z])",
    re.M,
)

# Theory subsection — «#### 1. Обозначение», not an exercise
_THEORY_HEADER = re.compile(
    r"^#{1,4}\s*\d+\.\s+[А-ЯA-ZЁ]",
    re.M,
)

# Number patterns (order matters — more specific first)
_NUM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\*\*(\d{1,4})\.\*\*"),           # **14.**
    re.compile(r"^\s*(\d{1,4})\)\s+", re.M),       # 14)
    re.compile(r"^\s*(\d{1,4})\.\s+", re.M),       # 14.
    re.compile(r"^\s*(\d{1,4})\s*[.)]\s+", re.M),   # 14. / 14)
    re.compile(r"^\s*(\d{1,4})\s+[-–—]\s+", re.M),  # 14 —
)

_MAX_EXercise_NUM = 5000
_LOCAL_MAX = 200  # local § numbering rarely exceeds this


@dataclass(frozen=True)
class ResolvedRange:
    lo: int
    hi: int
    count: int
    method: str
    confidence: float


def _exercise_body(text: str) -> str:
    """Return OCR fragment where exercises live (after «упражнения» marker)."""
    if not text or not text.strip():
        return ""
    m = _EXERCISE_SECTION.search(text)
    body = text[m.start():] if m else text
    stop = _SECTION_STOP.search(body, pos=80)
    if stop:
        body = body[: stop.start()]
    return body


def _line_is_theory(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # Only markdown theory subheadings — not exercise lines «1. Вычислите …»
    return bool(_THEORY_HEADER.match(s))


def collect_exercise_numbers(text: str, *, exercise_only: bool = True) -> list[int]:
    """Ordered list of exercise numbers found in text (may repeat)."""
    if not text or not text.strip():
        return []

    source = _exercise_body(text) if exercise_only else text
    if not source.strip() and exercise_only:
        source = text

    lines = source.splitlines()
    found: list[int] = []

    for line in lines:
        if _line_is_theory(line):
            continue
        matched = False
        for pat in _NUM_PATTERNS:
            if matched:
                break
            for mm in pat.finditer(line):
                n = int(mm.group(1))
                if 1 <= n <= _MAX_EXercise_NUM:
                    found.append(n)
                    matched = True
                    break

    return found


def _unique_sorted(nums: list[int]) -> list[int]:
    return sorted(set(nums))


def _looks_local(nums: list[int]) -> bool:
    if len(nums) < 2:
        return False
    lo, hi = nums[0], nums[-1]
    if lo > 15:
        return False
    if hi > _LOCAL_MAX:
        return False
    # starts near 1 and hi reflects real § span (e.g. 1…25)
    if lo <= 5:
        return True
    span = hi - lo + 1
    return len(nums) >= max(2, span // 4)


def _looks_global(nums: list[int], prev_hi: int | None) -> bool:
    if not nums:
        return False
    if prev_hi is None:
        return nums[-1] > 15 or len(nums) >= 5
    return nums[0] > prev_hi


def _map_local_to_global(local: list[int], prev_hi: int) -> tuple[int, int]:
    lo, hi = min(local), max(local)
    return prev_hi + lo, prev_hi + hi


def _range_from_list(nums: list[int], method: str, confidence: float) -> ResolvedRange | None:
    if not nums:
        return None
    u = _unique_sorted(nums)
    lo, hi = u[0], u[-1]
    return ResolvedRange(
        lo=lo,
        hi=hi,
        count=hi - lo + 1,
        method=method,
        confidence=confidence,
    )


def resolve_paragraph_range(
    text: str,
    *,
    prev_hi: int | None = None,
) -> ResolvedRange | None:
    """Best-effort exercise range for one § OCR text.

    Priority: global numbers > local mapped > count-only estimate.
    """
    if not text or not text.strip():
        return None

    in_section = collect_exercise_numbers(text, exercise_only=True)
    in_full = collect_exercise_numbers(text, exercise_only=False)

    # ── 1. Global continuous (numbers above previous §) ───────────────────
    if prev_hi is not None:
        global_from_section = _unique_sorted([n for n in in_section if n > prev_hi])
        if len(global_from_section) >= 2 and _looks_global(global_from_section, prev_hi):
            return _range_from_list(global_from_section, "global_section", 0.95)

        global_from_full = _unique_sorted([n for n in in_full if n > prev_hi])
        if len(global_from_full) >= 2 and _looks_global(global_from_full, prev_hi):
            return _range_from_list(global_from_full, "global_full", 0.85)

        if len(global_from_section) == 1 and global_from_section[0] > prev_hi:
            n = global_from_section[0]
            return ResolvedRange(n, n, 1, "global_single", 0.7)

    elif in_section:
        u = _unique_sorted(in_section)
        if len(u) >= 2:
            return _range_from_list(u, "global_first", 0.9)

    # ── 2. Local § numbering → map with prev_hi ───────────────────────────
    if prev_hi is not None:
        for src, label, conf in (
            (in_section, "local_section", 0.88),
            (in_full, "local_full", 0.75),
        ):
            u = _unique_sorted(src)
            if not u or u[0] > 15:
                continue
            lo_l, hi_l = u[0], u[-1]
            span = hi_l - lo_l + 1
            # Sparse markers (1, 3, 7) — count detected exercises only
            if lo_l <= 5 and span > len(u) * 1.5 and hi_l <= lo_l + len(u) * 2:
                count = len(u)
                return ResolvedRange(
                    lo=prev_hi + 1,
                    hi=prev_hi + count,
                    count=count,
                    method="count_sparse",
                    confidence=0.62,
                )
            if _looks_local(u):
                glo, ghi = _map_local_to_global(u, prev_hi)
                return ResolvedRange(
                    lo=glo,
                    hi=ghi,
                    count=ghi - glo + 1,
                    method=label,
                    confidence=conf,
                )

    # ── 3. Count-only: markers in exercise block, no reliable numbers ─────
    if prev_hi is not None and in_section:
        count = len(_unique_sorted(in_section))
        if count >= 2:
            return ResolvedRange(
                lo=prev_hi + 1,
                hi=prev_hi + count,
                count=count,
                method="count_section",
                confidence=0.55,
            )

    # ── 4. First § / no prev: use any plausible block ─────────────────────
    if prev_hi is None and in_full:
        u = _unique_sorted(in_full)
        if len(u) >= 3:
            return _range_from_list(u, "fallback_full", 0.5)

    return None


def fill_sequential_gaps(
    ordered_keys: list[str],
    ranges: dict[str, tuple[int, int]],
    *,
    meta: dict[str, ResolvedRange] | None = None,
) -> dict[str, tuple[int, int]]:
    """Fill missing § by interpolating from neighbors (global numbering books)."""
    out = dict(ranges)
    resolved_meta = meta or {}

    for i, key in enumerate(ordered_keys):
        if key in out:
            continue
        prev_hi = out[ordered_keys[j]][1] if (j := _prev_filled(ordered_keys, out, i)) is not None else None
        next_lo = out[ordered_keys[k]][0] if (k := _next_filled(ordered_keys, out, i)) is not None else None

        if prev_hi is not None and next_lo is not None and next_lo > prev_hi + 1:
            lo, hi = prev_hi + 1, next_lo - 1
            if hi >= lo:
                out[key] = (lo, hi)
                resolved_meta[key] = ResolvedRange(
                    lo, hi, hi - lo + 1, "interpolated", 0.4,
                )
        elif prev_hi is not None and i == len(ordered_keys) - 1:
            # last § — can't interpolate forward
            pass

    return out


def _prev_filled(keys: list[str], ranges: dict[str, tuple[int, int]], i: int) -> int | None:
    for j in range(i - 1, -1, -1):
        if keys[j] in ranges:
            return j
    return None


def _next_filled(keys: list[str], ranges: dict[str, tuple[int, int]], i: int) -> int | None:
    for j in range(i + 1, len(keys)):
        if keys[j] in ranges:
            return j
    return None


# ── Legacy API (used by build script / tests) ───────────────────────────────

def extract_exercise_numbers(text: str) -> set[int]:
    return set(collect_exercise_numbers(text, exercise_only=False))


def range_from_numbers(nums: set[int]) -> tuple[int, int] | None:
    if not nums:
        return None
    return min(nums), max(nums)
