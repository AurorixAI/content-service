"""Detect unsplit compound (batch) tasks — shared by split, smart_verify, audit."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_MCQ_HEADER_RE = re.compile(
    r"(?:какое|какой|какая|какие|выберите|укажите|установите\s+соответствие"
    r"|выбери|отметьте|определите\s+верн)",
    re.I,
)
_MCQ_OPTIONS_RE = re.compile(
    r"(?:^|\n)\s*[АБВГДABCDE]\)\s+",
    re.MULTILINE,
)
_ITEM_NUM_RE = re.compile(
    r"(?:^|[;\n|])\s*(\d+)\)\s+(.*?)(?=[;\n|]\s*\d+\)|\Z)",
    re.DOTALL,
)
_ITEM_LETTER_RE = re.compile(
    r"(?:^|[:\n;|])\s*([абвг])\)\s+(.*?)(?=[:\n;|]\s*[абвг]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_ANS_NUM_RE = re.compile(r"\d+\)\s*(.*?)(?=\s*[;,\n]\s*\d+\)|\Z)", re.DOTALL)
_ANS_LETTER_RE = re.compile(
    r"[абвг]\)\s*(.*?)(?=\s*[;,\n]\s*[абвг]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_LABELED_ANS_RE = re.compile(r"(?:^|[;\s])[дежз]\)\s*", re.I)
# Subitem label д)е)ж)з) — not inside Russian words (e.g. «в кубе)»).
_G8_SUBITEM_LABEL_RE = re.compile(r"(?<![а-яёА-ЯЁ])[дежз]\)", re.I)


@dataclass
class CompoundDetectResult:
    """Result of compound-task analysis."""

    should_split: bool = False
    is_split_child: bool = False
    nested_compound: bool = False  # split_from set but still multi-part
    is_mcq: bool = False
    skip_reason: str = ""
    pattern: str = "none"  # g8_dezhz | numeric_12 | letter_ab | multipart_answer
    n_subitems: int = 0
    exam_unsafe: bool = False
    warning: str = ""
    child_ids: list[str] = field(default_factory=list)


def _extract_items(text: str, pattern: re.Pattern, *, first_token: str) -> tuple[str, list[str]]:
    text = text.strip()
    matches = list(pattern.finditer(text))
    if not matches:
        return text, []
    tokens = [m.group(1).lower() for m in matches]
    if tokens[0] != first_token or len(matches) < 2:
        return text, []
    header_end = matches[0].start()
    header = text[:header_end].rstrip() if header_end > 0 else ""
    items: list[str] = []
    for i, m in enumerate(matches):
        body = m.group(2).strip()
        body = body.rstrip(".;,") if i == len(matches) - 1 else body.rstrip(";,")
        items.append(body)
    return header, items


def _parse_question(qtext: str) -> tuple[str, list[str]]:
    header, items = _extract_items(qtext, _ITEM_NUM_RE, first_token="1")
    if len(items) >= 2:
        return header, items
    return _extract_items(qtext, _ITEM_LETTER_RE, first_token="а")


def _parse_answers_num(ans: str) -> list[str]:
    if not ans or not ans.strip():
        return []
    return [m.group(1).strip().rstrip(";,") for m in _ANS_NUM_RE.finditer(ans.strip())]


def _parse_answers_letter(ans: str) -> list[str]:
    if not ans or not ans.strip():
        return []
    return [m.group(1).strip().rstrip(";,") for m in _ANS_LETTER_RE.finditer(ans.strip())]


def _parse_answers(ans: str, *, letter_mode: bool) -> list[str]:
    if letter_mode:
        parts = _parse_answers_letter(ans)
        if len(parts) >= 2:
            return parts
    parts = _parse_answers_num(ans)
    if len(parts) >= 2:
        return parts
    if letter_mode:
        return parts
    return _parse_answers_letter(ans)


def _parse_g8_multiline_compound(qtext: str, ans: str) -> tuple[str, list[str], list[str]] | None:
    if not _G8_SUBITEM_LABEL_RE.search(qtext):
        return None
    header_m = re.match(r"^([^\n]+:)", qtext.strip())
    header = header_m.group(1).strip() if header_m else ""
    body = qtext.strip()
    if header and body.startswith(header):
        body = body[len(header):].strip()

    q_segments: list[tuple[str, str]] = []
    for seg in re.split(r"(?=(?<![а-яёА-ЯЁ])[дежз]\)\s*)", body, flags=re.I):
        seg = seg.strip().strip(";")
        if not seg:
            continue
        m = re.match(r"^([дежз])\)\s*(.*)$", seg, re.I | re.S)
        if m:
            q_segments.append((m.group(1).lower(), m.group(2).strip()))
        else:
            q_segments.append(("", seg))
    if len(q_segments) < 2:
        return None

    a_map: dict[str, str] = {}
    a_unlabeled: list[str] = []
    for part in re.split(r"\s*;\s*", ans or ""):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([дежз])\)\s*(.*)$", part, re.I | re.S)
        if m:
            a_map[m.group(1).lower()] = m.group(2).strip()
        else:
            a_unlabeled.append(part)

    a_items: list[str] = []
    unlabeled_idx = 0
    for label, _qtext in q_segments:
        if label and label in a_map:
            a_items.append(a_map[label])
        elif not label and unlabeled_idx < len(a_unlabeled):
            a_items.append(a_unlabeled[unlabeled_idx])
            unlabeled_idx += 1
        else:
            a_items.append("")

    if not any(a_items):
        return None
    return header, [t for _l, t in q_segments], a_items


def _question_uses_letters(qtext: str) -> bool:
    _, letter_items = _extract_items(qtext, _ITEM_LETTER_RE, first_token="а")
    if len(letter_items) >= 2:
        return True
    _, num_items = _extract_items(qtext, _ITEM_NUM_RE, first_token="1")
    return len(num_items) < 2


def _is_mcq(question_text: str, answer_type: str, correct_answer: str) -> bool:
    header, items = _parse_question(question_text)
    letter_mode = _question_uses_letters(question_text)
    if len(items) >= 2:
        ans_parts = _parse_answers(correct_answer, letter_mode=letter_mode)
        if len(ans_parts) >= 2:
            return False
    if answer_type == "multiple_choice":
        if correct_answer and len(_parse_answers(correct_answer, letter_mode=False)) >= 2:
            return False
        if correct_answer and len(_parse_answers_letter(correct_answer)) >= 2:
            return False
        return True
    if _MCQ_HEADER_RE.search(question_text[:120]):
        return True
    if len(_MCQ_OPTIONS_RE.findall(question_text)) >= 2:
        return True
    return False


def _multipart_answer_parts(answer: str) -> list[str]:
    """Semicolon-separated answer with optional д)/е) labels."""
    if not answer:
        return []
    if _LABELED_ANS_RE.search(answer):
        parts = []
        for part in re.split(r"\s*;\s*", answer):
            part = re.sub(r"^[дежз]\)\s*", "", part.strip(), flags=re.I)
            if part:
                parts.append(part)
        return parts
    if ";" in answer:
        return [p.strip() for p in answer.split(";") if p.strip()]
    return []


def plan_split_items(
    task_id: str,
    question_text: str,
    correct_answer: str,
    answer_type: str = "exact_number",
    exercise_number: str = "",
) -> CompoundDetectResult:
    """Full split plan (same logic as split_compound_tasks.split_task)."""
    qtext = question_text or ""
    ans = correct_answer or ""
    atype = (answer_type or "exact_number").lower()
    parent_ex = str(exercise_number or "").strip()

    if _is_mcq(qtext, atype, ans):
        return CompoundDetectResult(is_mcq=True, skip_reason="MCQ")

    g8 = _parse_g8_multiline_compound(qtext, ans)
    if g8:
        header, q_items, _a_items = g8
        n = len(q_items)
        child_ids = [
            f"{task_id}.{i}" if len(f"{task_id}.{i}") <= 60 else f"{task_id[:55]}.{i}"
            for i in range(1, n + 1)
        ]
        return CompoundDetectResult(
            should_split=True,
            pattern="g8_dezhz",
            n_subitems=n,
            exam_unsafe=True,
            child_ids=child_ids,
            warning=f"G8 batch: {n} подпунктов (д)е)ж)з) — нужен split перед экзаменом/диагностикой",
        )

    letter_mode = _question_uses_letters(qtext)
    header, items = _parse_question(qtext)
    if len(items) >= 2:
        pat = "letter_ab" if letter_mode else "numeric_12"
        n = len(items)
        child_ids = [
            f"{task_id}.{i}" if len(f"{task_id}.{i}") <= 60 else f"{task_id[:55]}.{i}"
            for i in range(1, n + 1)
        ]
        return CompoundDetectResult(
            should_split=True,
            pattern=pat,
            n_subitems=n,
            exam_unsafe=True,
            child_ids=child_ids,
            warning=f"Compound {pat}: {n} подпунктов — нужен split",
        )

    # Hidden: multipart answer without clear Q markers (OCR glued answer only)
    mp = _multipart_answer_parts(ans)
    if len(mp) >= 2 and (re.search(r"[абвг]\)", ans, re.I) or _LABELED_ANS_RE.search(ans)):
        return CompoundDetectResult(
            should_split=True,
            pattern="multipart_answer",
            n_subitems=len(mp),
            exam_unsafe=True,
            warning=f"Multipart answer ({len(mp)} частей) без split — проверить вручную",
        )

    return CompoundDetectResult(skip_reason="no_subitems")


def detect_compound(
    *,
    task_id: str,
    question_text: str,
    correct_answer: str,
    answer_type: str = "exact_number",
    tags: dict | None = None,
    exercise_number: str = "",
) -> CompoundDetectResult:
    """
    Detect if task is an unsplit compound unsuitable for exam/diagnostic as-is.

    Split children (tags.split_from) are safe only when no longer multi-part.
    A first-level child like G8_TB_11_274.4 with д)е) answers still needs split.
    """
    tags = tags or {}
    if tags.get("compound_split_ok"):
        return CompoundDetectResult(skip_reason="marked_ok")

    plan = plan_split_items(
        task_id=task_id,
        question_text=question_text,
        correct_answer=correct_answer,
        answer_type=answer_type,
        exercise_number=exercise_number,
    )

    split_from = tags.get("split_from")
    if split_from and plan.should_split and plan.exam_unsafe:
        plan.is_split_child = True
        plan.nested_compound = True
        plan.warning = (
            f"Nested compound (from {split_from}): {plan.n_subitems} подпунктов — "
            f"нужен 2-й split перед экзаменом/диагностикой"
        )
        return plan

    if split_from:
        return CompoundDetectResult(
            is_split_child=True,
            skip_reason="split_child",
            warning="",
        )

    if plan.should_split:
        return plan
    return plan


def apply_compound_tags(tags: dict, result: CompoundDetectResult) -> dict:
    """Write compound detection into task tags."""
    tags = dict(tags)
    if result.is_split_child:
        tags.pop("needs_compound_split", None)
        tags.pop("compound_warning", None)
        return tags
    if result.should_split and result.exam_unsafe:
        tags["needs_compound_split"] = True
        tags["compound_pattern"] = result.pattern
        tags["compound_subitems"] = result.n_subitems
        tags["compound_warning"] = result.warning[:500]
        if result.nested_compound:
            tags["compound_nested"] = True
        else:
            tags.pop("compound_nested", None)
        if result.child_ids:
            tags["compound_planned_children"] = result.child_ids[:12]
    else:
        tags.pop("needs_compound_split", None)
        tags.pop("compound_warning", None)
        tags.pop("compound_pattern", None)
        tags.pop("compound_subitems", None)
    return tags
