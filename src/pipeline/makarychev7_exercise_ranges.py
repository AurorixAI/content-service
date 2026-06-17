"""Exercise number ranges per paragraph — Makarychev Algebra 7 (2023, 15th ed.).

Used by TaskExtractor to assign correct exercise_number and filter cross-paragraph bleed.
"""
from __future__ import annotations

# paragraph_number → (first_exercise, last_exercise)
MAKARYCHEV7_EXERCISE_RANGES: dict[int, tuple[int, int]] = {
    1: (1, 13),
    2: (14, 36),
    3: (37, 65),
    4: (66, 88),
    5: (89, 103),
    6: (104, 129),
    7: (130, 144),
    8: (145, 162),
    9: (163, 186),
    10: (187, 197),
    11: (247, 257),
    12: (258, 266),
    13: (267, 282),
    14: (283, 296),
    15: (297, 312),
    16: (313, 342),
    17: (343, 353),
    18: (386, 417),
    19: (418, 442),
    20: (443, 469),
    21: (470, 481),
    22: (482, 498),
    23: (499, 514),
    24: (515, 525),
    25: (583, 600),
    26: (601, 629),
    27: (630, 669),
    28: (670, 692),
    29: (693, 723),
    30: (724, 737),
    31: (738, 749),
    32: (815, 839),
    33: (840, 869),
    34: (870, 899),
    35: (900, 929),
    36: (930, 959),
    37: (960, 989),
    38: (990, 1019),
    39: (1020, 1040),
    40: (1041, 1060),
    41: (1061, 1071),
    42: (1072, 1083),
    43: (1084, 1097),
    44: (1098, 1114),
    45: (1115, 1143),
    46: (1144, 1152),
}

# Paragraphs whose last exercises spill onto the next paragraph's first page (OCR overlap).
MAKARYCHEV7_PAGE_END_OVERRIDE: dict[int, int] = {
    1: 11,  # упр. 10–13 on p.11; §2 also starts p.11
}


def exercise_range(paragraph_number: str | int) -> tuple[int, int] | None:
    try:
        n = int(paragraph_number)
    except (TypeError, ValueError):
        return None
    return MAKARYCHEV7_EXERCISE_RANGES.get(n)


def parse_exercise_num(raw: str) -> int | None:
    if not raw:
        return None
    m = __import__("re").match(r"^(\d+)", str(raw).strip())
    return int(m.group(1)) if m else None
