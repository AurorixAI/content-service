"""Question deduplication helpers for gap-fill / content-first ingest."""
from __future__ import annotations

import re


def normalize_question(text: str) -> str:
    """Aggressive normalization — ловит перефраз одной задачи."""
    t = (text or "").lower()
    t = re.sub(r"\$[^$]*\$", " ", t)
    t = re.sub(r"\[figure[^\]]*\]", " ", t, flags=re.I)
    t = re.sub(r"рис\.?\s*\d+", "рис", t)
    t = re.sub(r"на\s+рисунке", "на рис", t)
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def question_fingerprint(text: str) -> str:
    return normalize_question(text)[:240]


def _word_set(text: str) -> set[str]:
    return {w for w in normalize_question(text).split() if len(w) > 2}


def questions_match(a: str, b: str, *, threshold: float = 0.72) -> bool:
    """True if two question texts are the same task (exact or word overlap)."""
    if not a or not b:
        return False
    if question_fingerprint(a) == question_fingerprint(b):
        return True
    wa, wb = _word_set(a), _word_set(b)
    if len(wa) < 4 or len(wb) < 4:
        return False
    overlap = len(wa & wb) / max(len(wa | wb), 1)
    return overlap >= threshold


def questions_same_task(a: str, b: str) -> bool:
    """Strict match for cleanup — exact fp or ≥90% word overlap."""
    return questions_match(a, b, threshold=0.90)


def is_duplicate_question(text: str, known: set[str]) -> bool:
    """True if text matches any known fingerprint (exact or high word overlap)."""
    fp = question_fingerprint(text)
    if not fp:
        return False
    if fp in known:
        return True
    words = _word_set(text)
    if len(words) < 4:
        return False
    for prev in known:
        prev_words = set(prev.split())
        if len(prev_words) < 4:
            continue
        overlap = len(words & prev_words) / max(len(words | prev_words), 1)
        if overlap >= 0.72:
            return True
    return False
