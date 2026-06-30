"""Detect and repair compound/OCR garbage — orphan tails, stale tags, broken batches."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.pipeline.compound_detect import (
    _LABELED_ANS_RE,
    apply_compound_tags,
    detect_compound,
)

_ORPHAN_Q_TAIL_RE = re.compile(r";\s*[дежзи]\)", re.I)
_LABELED_Q_TAIL_RE = re.compile(r";\s*[абвг]\)", re.I)
_NUMERIC_BATCH_ANS_RE = re.compile(r"\d+\)\s*")


class CompoundIssue(str, Enum):
    OK = "ok"
    STALE_TAG = "stale_tag"
    ORPHAN_TAIL = "orphan_tail"
    BROKEN_BATCH = "broken_batch"
    NEEDS_SPLIT = "needs_split"


@dataclass
class CompoundIssueResult:
    issue: CompoundIssue
    detail: str = ""
    trimmed_question: str | None = None


def _answer_looks_single(correct_answer: str) -> bool:
    ans = (correct_answer or "").strip()
    if not ans:
        return False
    if _LABELED_ANS_RE.search(ans):
        return False
    if re.search(r"[абвг]\)", ans, re.I):
        return False
    if _NUMERIC_BATCH_ANS_RE.search(ans):
        return False
    if ";" in ans:
        parts = [p.strip() for p in ans.split(";") if p.strip()]
        if len(parts) >= 2:
            return False
    return True


def trim_orphan_question_tail(question_text: str) -> tuple[str, bool]:
    """Cut OCR tail starting at '; д)' / '; е)' / … in question."""
    q = question_text or ""
    m = _ORPHAN_Q_TAIL_RE.search(q)
    if not m:
        m = _LABELED_Q_TAIL_RE.search(q)
    if not m:
        return q, False
    trimmed = q[: m.start()].rstrip().rstrip(";,")
    return trimmed, trimmed != q


def classify_compound_issue(
    *,
    task_id: str,
    question_text: str,
    correct_answer: str,
    answer_type: str,
    tags: dict | None,
    split_item_count: int = 0,
    split_second_answer_empty: bool = False,
) -> CompoundIssueResult:
    """Classify compound-related content issues for repair pipeline."""
    tags = dict(tags or {})
    q = question_text or ""
    a = correct_answer or ""

    cd = detect_compound(
        task_id=task_id,
        question_text=q,
        correct_answer=a,
        answer_type=answer_type,
        tags=tags,
    )

    tagged = tags.get("needs_compound_split") is True
    if tagged and not cd.should_split:
        return CompoundIssueResult(
            issue=CompoundIssue.STALE_TAG,
            detail="needs_compound_split set but task is atomic",
        )

    if tags.get("needs_content_repair"):
        return CompoundIssueResult(
            issue=CompoundIssue.BROKEN_BATCH,
            detail=tags.get("content_repair_reason") or "already marked",
        )

    if cd.should_split and split_item_count == 0:
        mp = _LABELED_ANS_RE.search(a) or re.search(r"[абвг]\)", a, re.I)
        if mp or _NUMERIC_BATCH_ANS_RE.search(a):
            return CompoundIssueResult(
                issue=CompoundIssue.BROKEN_BATCH,
                detail="multipart answer, question truncated — needs re-OCR",
            )

    if cd.should_split and split_item_count >= 2 and split_second_answer_empty:
        return CompoundIssueResult(
            issue=CompoundIssue.ORPHAN_TAIL,
            detail="compound split would leave empty child answer",
        )

    if _answer_looks_single(a) and (_ORPHAN_Q_TAIL_RE.search(q) or _LABELED_Q_TAIL_RE.search(q)):
        trimmed, changed = trim_orphan_question_tail(q)
        if changed:
            return CompoundIssueResult(
                issue=CompoundIssue.ORPHAN_TAIL,
                detail="OCR orphan tail in question",
                trimmed_question=trimmed,
            )

    if cd.should_split and cd.exam_unsafe:
        return CompoundIssueResult(
            issue=CompoundIssue.NEEDS_SPLIT,
            detail=cd.warning[:200],
        )

    return CompoundIssueResult(issue=CompoundIssue.OK)


def clear_compound_block_tags(tags: dict) -> dict:
    tags = dict(tags)
    for key in (
        "needs_compound_split",
        "compound_warning",
        "compound_pattern",
        "compound_subitems",
        "compound_nested",
        "compound_planned_children",
    ):
        tags.pop(key, None)
    return tags


def mark_content_repair(tags: dict, *, reason: str) -> dict:
    tags = dict(tags)
    tags["needs_content_repair"] = True
    tags["content_repair_reason"] = reason[:500]
    tags["smart_verify_status"] = "needs_content_repair"
    tags["answer_verify_mode"] = "needs_content_repair"
    for key in (
        "choices_complete",
        "distractor_regen_pending",
        "distractor_regen_exhausted",
        "smart_verify_retry_exhausted",
    ):
        tags.pop(key, None)
    return tags


def apply_orphan_trim_tags(tags: dict) -> dict:
    tags = clear_compound_block_tags(tags)
    tags["compound_repaired"] = "orphan_trim"
    tags["smart_verify_status"] = "pending"
    tags["answer_verify_mode"] = "pending"
    tags.pop("choices_complete", None)
    tags.pop("distractor_regen_pending", None)
    tags.pop("distractor_regen_exhausted", None)
    tags.pop("smart_verify_retry_exhausted", None)
    tags.pop("smart_verify_error", None)
    tags.pop("smart_verify_reason", None)
    return tags


def sync_compound_tags_from_detect(tags: dict, *, task_id: str, question_text: str,
                                   correct_answer: str, answer_type: str) -> dict:
    """Refresh compound tags from current detect state."""
    cd = detect_compound(
        task_id=task_id,
        question_text=question_text,
        correct_answer=correct_answer,
        answer_type=answer_type,
        tags=tags,
    )
    if cd.should_split:
        return apply_compound_tags(tags, cd)
    return clear_compound_block_tags(tags)
