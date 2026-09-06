#!/usr/bin/env python3
"""
Хирургическое разбиение склеенных задач (compound) прямо в БД.

Находит задачи вида:
  question_text = "Вычислите:\n1) 5+3\n2) 7*2"
  correct_answer = "1) 8; 2) 14"

  question_text = "Упростите:\nа) 2x+3\nб) x-1"
  correct_answer = "а) ...; б) ..."

Разбивает каждую на отдельные строки tasks_master без повторного OCR/Gemini.
Дистракторы у детей обнуляются — генерируются позже через finish_g8.py.

НЕ разбивает MCQ (multiple_choice / «Какое из» / А/Б/В/Г варианты).

Usage:
    docker exec content-worker python /app/scripts/split_compound_tasks.py --dry-run
    docker exec content-worker python /app/scripts/split_compound_tasks.py
    docker exec content-worker python /app/scripts/split_compound_tasks.py --textbook-ids b8f4a2c1
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.core.config import get_settings

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# ── Целевые учебники ─────────────────────────────────────────────────────────
ALL_TEXTBOOKS = {
    "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8": ("Математика 6 класс — Школьное издание", "G6_TB"),
    "4b19752a-3d54-4538-b6a6-26ce1fbb48fd": ("Алгебра 7 класс — Школьное издание",    "G7_ALG"),
    "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f": ("Алгебра 7 класс — Макарычев",            "G7_TB"),
    "184640af-64e7-47af-a974-8b8112e6ffb2": ("Математика 5 класс — Виленкин",           "G5_TB"),
    "5630a994-061d-4c20-9863-fe049c8059fb": ("Математика 5 класс — IDUM, часть 1",   "G5_TB"),
    "47167115-5961-4405-bb55-1bda8ce1b687": ("Математика 5 класс — IDUM, часть 2",   "G5_TB"),
    "351a95c1-5208-4ae9-8323-6d7dd5e8bb82": ("Математика 6 класс — Виленкин",           "G6_TB"),
    "e8f3a1b2-7c4d-5e6f-8091-2345678abcde": ("Алгебра 8 класс — Школьное издание",     "G8_ALG"),
    "b8f4a2c1-3d5e-4f60-9182-3456789abcde": ("Алгебра 8 класс — Макарычев",            "G8_TB"),
    "5a9f7fea-1394-4141-9d58-015972e83acc": ("Алгебра, 9 класс (Макарычев, 2023)",     "G9_TB"),
}

# ── MCQ-детектор: не разбивать если → тест/выбор ────────────────────────────
_MCQ_HEADER_RE = re.compile(
    r"(?:какое|какой|какая|какие|выберите|укажите|установите\s+соответствие"
    r"|выбери|отметьте|определите\s+верн)",
    re.I,
)
# Варианты MCQ: заглавные А) Б) В) или латинские A) B) — не путать с подпунктами а) б)
_MCQ_OPTIONS_RE = re.compile(
    r"(?:^|\n)\s*[АБВГДABCDE]\)\s+",
    re.MULTILINE,
)

# ── Подпункты: 1) 2) 3) или а) б) в) ────────────────────────────────────────
_ITEM_NUM_RE = re.compile(
    r"(?:^|[;\n|])\s*(\d+)\)\s+(.*?)(?=[;\n|]\s*\d+\)|\Z)",
    re.DOTALL,
)
_ITEM_LETTER_RE = re.compile(
    r"(?:^|[:\n;|])\s*([абвг])\)\s+(.*?)(?=[:\n;|]\s*[абвг]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_ITEM_LETTER_MIXED_RE = re.compile(
    r"(?:^|[:\n;|])\s*([a-zа-яё])\)\s*(.*?)(?=(?:;\s*[a-zа-яё]\)|(?:^|[:\n;|])\s*[a-zа-яё]\)|\Z))",
    re.DOTALL | re.IGNORECASE,
)
_ANS_NUM_RE = re.compile(r"\d+\)\s*(.*?)(?=\s*[;,\n]\s*\d+\)|\Z)", re.DOTALL)
_ANS_LETTER_RE = re.compile(
    r"[абвг]\)\s*(.*?)(?=\s*[;,\n]\s*[абвг]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_ANS_LETTER_MIXED_RE = re.compile(
    r"([a-zа-яё])\)\s*(.*?)(?=\s*[;,\n]\s*[a-zа-яё]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_ANS_LETTER_BLOCK_RE = re.compile(
    r"([а-яё])\)\s*(.*?)(?=\s+[а-яё]\)|\Z)",
    re.I | re.S,
)
_CHILD_ANS_LABEL_RE = re.compile(r"^[абвгдежзи]\)\s*", re.I)
_CHILD_Q_ORPHAN_RE = re.compile(r";\s*[а-яё]\)\s", re.I)
_ORDERING_ANS_RE = re.compile(r"^[а-яё](?:\s*,\s*[а-яё])+$", re.I)


def _extract_items(text: str, pattern: re.Pattern, *, first_token: str) -> tuple[str, list[str]]:
    """Return (header, [item1, item2, ...]) for numeric or letter markers."""
    text = text.strip()
    matches = list(pattern.finditer(text))
    if not matches:
        return text, []

    tokens = [m.group(1).lower() for m in matches]
    if tokens[0] != first_token:
        return text, []
    if len(matches) < 2:
        return text, []

    header_end = matches[0].start()
    if header_end > 0 and text[header_end] in ";\n|":
        header = text[:header_end].rstrip()
    else:
        header = text[:header_end].rstrip()

    items: list[str] = []
    for i, m in enumerate(matches):
        body = m.group(2).strip()
        if i == len(matches) - 1:
            body = body.rstrip(".;,")
        else:
            body = body.rstrip(";,")
        items.append(body)

    return header, items


def _extract_letter_items_mixed(text: str) -> tuple[str, list[str]]:
    text = text.strip()
    matches = list(_ITEM_LETTER_MIXED_RE.finditer(text))
    if len(matches) < 2:
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
    """Numeric 1) 2) first, then letter а) б) / mixed a) b)."""
    header, items = _extract_items(qtext, _ITEM_NUM_RE, first_token="1")
    if len(items) >= 2:
        return header, items
    header, items = _extract_letter_items_mixed(qtext)
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
    s = ans.strip()
    first = re.search(r"[а-яё]\)", s, re.I)
    if first and first.start() > 0:
        pre = s[: first.start()].strip().rstrip(";:")
        if pre and not re.match(r"^\d+\)", pre):
            s = s[first.start() :]
    parts = [m.group(2).strip().rstrip(";., ") for m in _ANS_LETTER_BLOCK_RE.finditer(s)]
    if len(parts) >= 2:
        return parts
    parts = [m.group(2).strip().rstrip(";,") for m in _ANS_LETTER_MIXED_RE.finditer(s)]
    if len(parts) >= 2:
        return parts
    return [m.group(1).strip().rstrip(";,") for m in _ANS_LETTER_RE.finditer(s)]


def _parse_labeled_qa_pairs(qtext: str, ans: str) -> list[tuple[str, str, str]] | None:
    """Aligned (label, question, answer) when both sides use а) б) в)."""
    ans_matches = list(_ANS_LETTER_BLOCK_RE.finditer((ans or "").strip()))
    if len(ans_matches) < 2:
        return None
    q_base_m = re.match(r"^(.*?)(?=\s*[а-яё]\))", qtext.strip(), re.I | re.S)
    q_base = (q_base_m.group(1).strip().rstrip(":") if q_base_m else "").strip()
    pairs: list[tuple[str, str, str]] = []
    for m in ans_matches:
        label = m.group(1).lower()
        aval = m.group(2).strip().rstrip(";., ")
        qm = re.search(
            rf"(?:^|[\s:]){re.escape(label)}\)\s*(.*?)(?=\s+[а-яё]\)|\Z)",
            qtext,
            re.I | re.S,
        )
        q_item = qm.group(1).strip().rstrip(";., ") if qm else ""
        if q_base and q_item:
            q_full = f"{q_base}\n{label}) {q_item}"
        elif q_base:
            q_full = f"{q_base}\n{label})"
        elif q_item:
            q_full = f"{label}) {q_item}"
        else:
            q_full = f"{label})"
        pairs.append((label, q_full.strip(), aval))
    return pairs if len(pairs) >= 2 else None


def _is_ordering_compound(qtext: str, ans: str) -> bool:
    """«Расположите в порядке…» с ответом «г, б, а, в, д» — одна задача, не split."""
    if not _ORDERING_ANS_RE.match((ans or "").strip()):
        return False
    return bool(re.search(r"расположите|упорядоч", qtext, re.I))


def _parse_numbered_section_compound(
    qtext: str, ans: str
) -> tuple[str, list[str], list[str]] | None:
    """
    «1) … а) … б) …  2) … а) …» — секции по 1)/2)/3) в ответе.
    Каждая секция → один child (ответ = все а)б)в) секции).
    """
    if not re.search(r"\b1\)\s*а\)", ans, re.I):
        return None
    header_m = re.match(r"^([^\n]+)", qtext.strip())
    header = header_m.group(1).strip() if header_m else ""
    a_sections: list[tuple[str, str]] = []
    for m in re.finditer(
        r"(\d+)\)\s*((?:[а-яё]\)[^;]*(?:;\s*)?)+)",
        ans,
        re.I | re.S,
    ):
        a_sections.append((m.group(1), m.group(2).strip().rstrip("; ")))
    if len(a_sections) < 2:
        return None
    q_sections: list[str] = []
    body = qtext.strip()
    if header and body.startswith(header):
        body = body[len(header) :].strip()
    for m in re.finditer(
        r"(\d+)\)\s*(.*?)(?=\n\s*\d+\)|\Z)",
        body,
        re.S,
    ):
        q_sections.append(m.group(2).strip())
    if len(q_sections) < len(a_sections):
        q_sections = re.split(r"\n\s*(?=\d+\))", body)
        q_sections = [re.sub(r"^\d+\)\s*", "", s).strip() for s in q_sections if s.strip()]
    if len(q_sections) < len(a_sections):
        return None
    return header, q_sections[: len(a_sections)], [a for _n, a in a_sections]


def _build_child_items(
    tid: str,
    parent_ex: str,
    atype: str,
    pairs: list[tuple[str, str, str]],
) -> list[dict]:
    items: list[dict] = []
    for i, (_label, q_full, aval) in enumerate(pairs, 1):
        sub_id = f"{tid}.{i}"
        if len(sub_id) > 60:
            sub_id = f"{tid[:55]}.{i}"
        sub_ex = f"{parent_ex}.{i}" if parent_ex else str(i)
        items.append({
            "id": sub_id,
            "question_text": q_full,
            "correct_answer": _clean_child_answer(aval),
            "exercise_number": sub_ex,
            "answer_type": atype,
        })
    return items


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
    """
    G8 textbook pattern: first item unmarked, then д) е) ж) з) in question.
    Answers matched by label when present, else positional for unlabeled head.
    """
    if not re.search(r"[дежз]\)", qtext, re.I):
        return None
    # Standard а)б)в)г) compounds — not the G8 «д)е)ж)з)» batch pattern.
    letter_matches = list(_ITEM_LETTER_MIXED_RE.finditer(qtext))
    if letter_matches and letter_matches[0].group(1).lower() in "абвг":
        return None
    header_m = re.match(r"^([^\n]+:)", qtext.strip())
    header = header_m.group(1).strip() if header_m else ""
    body = qtext.strip()
    if header and body.startswith(header):
        body = body[len(header):].strip()

    q_segments: list[tuple[str, str]] = []
    for seg in re.split(r"(?=\s*[дежз]\)\s*)", body, flags=re.I):
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

    q_items = [text for _label, text in q_segments]
    return header, q_items, a_items


def _infer_answer_type(header: str, question_text: str, fallback: str) -> str:
    """Correct misclassified set → expression / inequality from task header."""
    h = f"{header} {question_text[:120]}".lower()
    if re.search(r"преобразуйте|разложите|упростите|сократите|вычислите", h):
        return "expression"
    if re.search(r"неравенств", h):
        return "inequality"
    if re.search(r"уравнен", h):
        return "equation_solution"
    if fallback == "set" and re.search(r"многочлен|множител|дроб", h):
        return "expression"
    return fallback


def _question_uses_letters(qtext: str) -> bool:
    _, letter_items = _extract_letter_items_mixed(qtext)
    if len(letter_items) >= 2:
        return True
    _, letter_items = _extract_items(qtext, _ITEM_LETTER_RE, first_token="а")
    if len(letter_items) >= 2:
        return True
    _, num_items = _extract_items(qtext, _ITEM_NUM_RE, first_token="1")
    return len(num_items) < 2


def _split_from_labeled_answer(
    tid: str,
    qtext: str,
    ans: str,
    atype: str,
    parent_ex: str,
) -> list[dict] | None:
    """Answer has а) б) в) labels — align with question labels when possible."""
    pairs = _parse_labeled_qa_pairs(qtext, ans)
    if pairs:
        return _build_child_items(tid, parent_ex, atype, pairs)
    matches = list(_ANS_LETTER_BLOCK_RE.finditer((ans or "").strip()))
    if len(matches) < 2:
        return None
    q_base_m = re.match(r"^(.*?)(?=\s*[а-яё]\))", (qtext or "").strip(), re.I | re.S)
    q_base = (q_base_m.group(1).strip().rstrip(":") if q_base_m else (qtext or "").strip())
    split_items: list[dict] = []
    for i, m in enumerate(matches, 1):
        label = m.group(1)
        item_ans = m.group(2).strip().rstrip(";., ")
        sub_id = f"{tid}.{i}"
        if len(sub_id) > 60:
            sub_id = f"{tid[:55]}.{i}"
        q = f"{q_base}\n{label})" if q_base else f"{label})"
        sub_ex = f"{parent_ex}.{i}" if parent_ex else str(i)
        split_items.append({
            "id": sub_id,
            "question_text": q.strip(),
            "correct_answer": _clean_child_answer(item_ans),
            "exercise_number": sub_ex,
            "answer_type": atype,
        })
    return split_items


def _is_mcq(question_text: str, answer_type: str, correct_answer: str) -> bool:
    header, items = _parse_question(question_text)
    letter_mode = _question_uses_letters(question_text)

    # Structured per-item answers → compound, not MCQ
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


# ── Результат разбора ────────────────────────────────────────────────────────
@dataclass
class SplitResult:
    original_id: str
    items: list[dict]       # [{id, question_text, correct_answer, exercise_number}, ...]
    skip_reason: str = ""   # "" means split OK


def _clean_child_answer(ans: str) -> str:
    return _CHILD_ANS_LABEL_RE.sub("", (ans or "").strip()).strip()


def validate_split_quality(
    res: SplitResult,
    *,
    allow_empty_answers: bool = False,
) -> str | None:
    """Return skip reason when split would produce low-quality children."""
    if len(res.items) < 2:
        return "too_few_items"
    empty_idxs = [
        i for i, it in enumerate(res.items)
        if not (it.get("correct_answer") or "").strip()
    ]
    if empty_idxs:
        if allow_empty_answers and all(
            (it.get("question_text") or "").strip() for it in res.items
        ):
            pass
        elif len(empty_idxs) > 1 or (empty_idxs and empty_idxs[0] < len(res.items) - 1):
            return "empty_answers"
    for it in res.items:
        ans = (it.get("correct_answer") or "").strip()
        if _CHILD_ANS_LABEL_RE.match(ans):
            return "labeled_answer"
        q = it.get("question_text") or ""
        if _CHILD_Q_ORPHAN_RE.search(q):
            ans = (it.get("correct_answer") or "").strip()
            # Секция с несколькими а)б)в) в одном child — допустимо.
            if not (re.search(r"[а-яё]\)", ans, re.I) and q.count(")") >= 3):
                return "orphan_in_child_q"
    return None


def split_task(row: dict) -> SplitResult:
    tid     = row["id"]
    qtext   = row["question_text"] or ""
    ans     = row["correct_answer"] or ""
    atype   = row["answer_type"] or "exact_number"
    parent_ex = str(row.get("exercise_number") or "").strip()

    if _is_mcq(qtext, atype, ans):
        return SplitResult(tid, [], skip_reason="MCQ")

    if _is_ordering_compound(qtext, ans):
        return SplitResult(tid, [], skip_reason="ordering_whole")

    numbered = _parse_numbered_section_compound(qtext, ans)
    if numbered:
        header, q_items, a_items = numbered
        child_atype = _infer_answer_type(header, qtext, atype)
        split_items = []
        for i, (item_text, item_ans) in enumerate(zip(q_items, a_items), 1):
            sub_id = f"{tid}.{i}"
            if len(sub_id) > 60:
                sub_id = f"{tid[:55]}.{i}"
            q = f"{header}\n{i}) {item_text}" if header else f"{i}) {item_text}"
            sub_ex = f"{parent_ex}.{i}" if parent_ex else str(i)
            split_items.append({
                "id": sub_id,
                "question_text": q.strip(),
                "correct_answer": _clean_child_answer(item_ans),
                "exercise_number": sub_ex,
                "answer_type": child_atype,
            })
        return SplitResult(tid, split_items)

    pairs = _parse_labeled_qa_pairs(qtext, ans)
    if pairs:
        return SplitResult(
            tid,
            _build_child_items(tid, parent_ex, atype, pairs),
        )

    g8 = _parse_g8_multiline_compound(qtext, ans)
    if g8:
        header, q_items, a_items = g8
        child_atype = _infer_answer_type(header, qtext, atype)
        split_items = []
        for i, (item_text, item_ans) in enumerate(zip(q_items, a_items), 1):
            sub_id = f"{tid}.{i}"
            if len(sub_id) > 60:
                sub_id = f"{tid[:55]}.{i}"
            q = f"{header}\n{item_text}" if header else item_text
            sub_ex = f"{parent_ex}.{i}" if parent_ex else str(i)
            split_items.append({
                "id": sub_id,
                "question_text": q.strip(),
                "correct_answer": _clean_child_answer(item_ans),
                "exercise_number": sub_ex,
                "answer_type": child_atype,
            })
        return SplitResult(tid, split_items)

    letter_mode = _question_uses_letters(qtext)
    header, items = _parse_question(qtext)
    if len(items) < 2:
        labeled = _split_from_labeled_answer(tid, qtext, ans, atype, parent_ex)
        if labeled:
            return SplitResult(tid, labeled)
        return SplitResult(tid, [], skip_reason="no_subitems")

    answers = _parse_answers(ans, letter_mode=letter_mode)
    if len(answers) < len(items) and len(answers) >= 2:
        if len(answers) == len(items) - 1:
            answers = [""] + answers
    if len(answers) < len(items) and ";" in (ans or ""):
        semi = [p.strip() for p in (ans or "").split(";") if p.strip()]
        if len(semi) == len(items):
            answers = semi

    split_items = []
    _LABELS = "абвгдежз"
    for i, item_text in enumerate(items, 1):
        sub_id = f"{tid}.{i}"
        if len(sub_id) > 60:
            sub_id = f"{tid[:55]}.{i}"

        body = re.sub(r"^[a-zа-яё]\)\s*", "", item_text.strip(), flags=re.I)
        m_label = re.match(r"^([a-zа-яё])\)", item_text.strip(), re.I)
        label = m_label.group(1) if m_label else (
            _LABELS[i - 1] if i <= len(_LABELS) else str(i)
        )
        if header:
            q = f"{header}\n{label}) {body}"
        else:
            q = f"{label}) {body}"

        a = answers[i - 1] if i <= len(answers) else ""
        sub_ex = f"{parent_ex}.{i}" if parent_ex else str(i)

        split_items.append({
            "id":             sub_id,
            "question_text":  q.strip(),
            "correct_answer": _clean_child_answer(a),
            "exercise_number": sub_ex,
            "answer_type":    atype,
        })

    return SplitResult(tid, split_items)


def _parent_allows_empty_children(ans: str, qtext: str = "") -> bool:
    a = (ans or "").strip()
    if a in ("", "—", "-"):
        return True
    if re.search(r"придумайте|составьте", qtext or "", re.I):
        return True
    return False


# ── БД ───────────────────────────────────────────────────────────────────────

def fetch_compound_tasks(
    engine: Engine,
    textbook_id: str,
    *,
    tagged_only: bool = False,
    skip_content_repair: bool = True,
) -> list[dict]:
    tagged_clause = (
        "COALESCE(tm.tags->>'needs_compound_split', 'false') = 'true'"
        if tagged_only
        else """(
                    COALESCE(tm.tags->>'needs_compound_split', 'false') = 'true'
                    OR (tm.question_text LIKE '%%1)%%' AND tm.question_text LIKE '%%2)%%')
                    OR (
                        tm.question_text ~* '(^|[;\\n|])[[:space:]]*[а-г]\\)'
                        AND tm.question_text ~* '(^|[;\\n|])[[:space:]]*[б-г]\\)'
                    )
                    OR (
                        tm.question_text ~* '[[:space:]:][[:space:]]*[а-г]\\)'
                        AND tm.correct_answer ~* '[а-г]\\)'
                    )
                    OR (
                        tm.question_text ~* '[дежз]\\)'
                        AND tm.correct_answer LIKE '%%;%%'
                    )
                )"""
    )
    repair_clause = (
        "AND COALESCE(tm.tags->>'needs_content_repair', 'false') != 'true'"
        if skip_content_repair
        else ""
    )
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT tm.id, tm.question_text, tm.correct_answer,
                       tm.answer_type, tm.skill_id, tm.toc_id,
                       tm.difficulty, tm.cognitive_load, tm.source_type,
                       tm.is_star, tm.task_category, tm.tags,
                       tm.distractor_meta,
                       tm.answer_options, tm.question_latex, tm.question_image_url,
                       tm.source_reference, tm.verification_status,
                       tt.paragraph_number, tt.exercise_number
                FROM tasks_master tm
                JOIN textbook_tasks tt
                  ON tt.task_id = tm.id
                 AND tt.textbook_id = CAST(:tid AS UUID)
                WHERE {tagged_clause}
                {repair_clause}
                ORDER BY tm.id
            """),
            {"tid": textbook_id},
        ).mappings().fetchall()
    return [dict(r) for r in rows]


def _child_tags(parent_tags: dict | None, original_id: str) -> dict:
    tags = dict(parent_tags or {})
    tags["split_from"] = original_id
    tags["smart_verify_status"] = "pending"
    for key in (
        "answer_beautified",
        "choices_complete",
        "distractor_regen_pending",
        "smart_verify_reason",
        "needs_compound_split",
        "needs_content_repair",
        "compound_warning",
        "compound_pattern",
        "compound_subitems",
        "compound_planned_children",
        "compound_nested",
    ):
        tags.pop(key, None)
    tags["compound_split_ok"] = True
    return tags


def apply_split(engine: Engine, textbook_id: str, results: list[SplitResult],
                dry_run: bool) -> tuple[int, int]:
    """Returns (n_deleted, n_inserted)."""
    n_del = 0
    n_ins = 0

    for res in results:
        if not res.items:
            continue

        if dry_run:
            n_del += 1
            n_ins += len(res.items)
            continue

        with engine.begin() as conn:
            # Query figure references of the parent task to copy to children
            fig_res = conn.execute(
                text("SELECT figure_id FROM task_figure_refs WHERE task_id = :parent_id"),
                {"parent_id": res.original_id}
            )
            parent_figures = [fr[0] for fr in fig_res.all()]

            for item in res.items:
                try:
                    conn.execute(
                        text("""
                            INSERT INTO tasks_master (
                                id, skill_id, question_text, question_latex, question_image_url,
                                answer_type, correct_answer,
                                difficulty, cognitive_load, source_type, is_star, task_category,
                                tags, distractor_meta, answer_options,
                                source_reference, verification_status, toc_id
                            ) VALUES (
                                :id, :skill_id, :question_text, :question_latex, :question_image_url,
                                :answer_type, :correct_answer,
                                :difficulty, :cognitive_load, :source_type, :is_star, :task_category,
                                CAST(:tags AS jsonb), CAST(:dmeta AS jsonb),
                                CAST(:aopts AS jsonb),
                                :source_reference, :verification_status, :toc_id
                            )
                            ON CONFLICT (id) DO NOTHING
                        """),
                        {
                            "id":                  item["id"],
                            "skill_id":            res._row["skill_id"],
                            "question_text":       item["question_text"],
                            "question_latex":      "",
                            "question_image_url":  res._row.get("question_image_url"),
                            "answer_type":         item.get("answer_type") or _infer_answer_type(
                                "", item.get("question_text", ""), res._row["answer_type"]
                            ),
                            "correct_answer":      item["correct_answer"],
                            "difficulty":          res._row["difficulty"],
                            "cognitive_load":      res._row.get("cognitive_load") or "apply",
                            "source_type":         res._row["source_type"],
                            "is_star":             bool(res._row.get("is_star")),
                            "task_category":       res._row.get("task_category") or "standard",
                            "tags":                json.dumps(
                                _child_tags(res._row.get("tags"), res.original_id),
                                ensure_ascii=False,
                            ),
                            "dmeta":               json.dumps([]),
                            "aopts":               json.dumps([]),
                            "source_reference":    res._row.get("source_reference"),
                            "verification_status": "pending",
                            "toc_id":              res._row["toc_id"],
                        },
                    )

                    conn.execute(
                        text("""
                            INSERT INTO textbook_tasks
                              (textbook_id, task_id, paragraph_number, exercise_number)
                            VALUES
                              (CAST(:tb_id AS UUID), :task_id, :para, :ex)
                            ON CONFLICT DO NOTHING
                        """),
                        {
                            "tb_id":   textbook_id,
                            "task_id": item["id"],
                            "para":    res._row.get("paragraph_number"),
                            "ex":      item["exercise_number"],
                        },
                    )

                    # Copy figure references to the child task
                    for fig_id in parent_figures:
                        conn.execute(
                            text("INSERT INTO task_figure_refs (task_id, figure_id) VALUES (:child_id, :fig_id) ON CONFLICT DO NOTHING"),
                            {"child_id": item["id"], "fig_id": fig_id}
                        )
                        
                    n_ins += 1
                except Exception as exc:
                    log.error("Insert %s failed: %s", item["id"], exc)

            conn.execute(
                text("DELETE FROM textbook_tasks WHERE task_id = :tid AND textbook_id = CAST(:tb_id AS UUID)"),
                {"tid": res.original_id, "tb_id": textbook_id},
            )
            conn.execute(
                text("DELETE FROM tasks_master WHERE id = :tid"),
                {"tid": res.original_id},
            )
            n_del += 1

    return n_del, n_ins


def _tag_split_reject(engine: Engine, row: dict, reason: str) -> None:
    from src.pipeline.compound_repair import mark_content_repair

    tags = row.get("tags") if isinstance(row.get("tags"), dict) else {}
    new_tags = mark_content_repair(
        tags,
        reason=f"split rejected: {reason}",
    )
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE tasks_master SET tags = CAST(:tags AS jsonb) WHERE id = :id"),
            {"id": row["id"], "tags": json.dumps(new_tags, ensure_ascii=False)},
        )


def process_textbook(
    engine: Engine,
    textbook_id: str,
    title: str,
    dry_run: bool,
    *,
    tagged_only: bool = False,
    skip_content_repair: bool = True,
    tag_bad_splits: bool = True,
) -> None:
    rows = fetch_compound_tasks(
        engine,
        textbook_id,
        tagged_only=tagged_only,
        skip_content_repair=skip_content_repair,
    )
    log.info("%s: %d compound candidates", title, len(rows))

    results = []
    stats: dict[str, int] = {"split": 0, "items_total": 0}

    for row in rows:
        res = split_task(row)
        object.__setattr__(res, "_row", row)
        if res.skip_reason:
            key = res.skip_reason.lower()
            stats[key] = stats.get(key, 0) + 1
            results.append(res)
            continue
        q_issue = validate_split_quality(res)
        if q_issue:
            log.warning("  REJECT %s (%s)", row["id"], q_issue)
            stats[q_issue] = stats.get(q_issue, 0) + 1
            if tag_bad_splits and not dry_run:
                _tag_split_reject(engine, row, q_issue)
            res = SplitResult(res.original_id, [], skip_reason=q_issue)
        else:
            stats["split"] += 1
            stats["items_total"] += len(res.items)
        results.append(res)

    log.info(
        "  Plan: %d to split → %d sub-tasks | %d MCQ kept | %d no-subitems | %d rejected",
        stats["split"],
        stats["items_total"],
        stats.get("mcq", 0),
        stats.get("no_subitems", 0),
        sum(v for k, v in stats.items() if k not in {"split", "items_total", "mcq", "no_subitems"}),
    )

    if dry_run:
        shown = 0
        for res in results:
            if shown >= 3 or not res.items:
                continue
            log.info("  EXAMPLE: %s → %s", res.original_id, [i["id"] for i in res.items])
            log.info("    q[0]: %s", res.items[0]["question_text"][:80])
            log.info("    ans[0]: %s", res.items[0]["correct_answer"][:60])
            log.info("    ex[0]: %s", res.items[0]["exercise_number"])
            shown += 1
        log.info("  [DRY-RUN] no DB changes")
        return

    n_del, n_ins = apply_split(engine, textbook_id, results, dry_run=False)
    log.info("  Done: %d original deleted, %d sub-tasks inserted", n_del, n_ins)

    with engine.begin() as conn:
        cnt = conn.execute(
            text("""
                SELECT COUNT(*) FROM textbook_tasks
                WHERE textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": textbook_id},
        ).scalar()
        conn.execute(
            text("""
                UPDATE textbooks SET tasks_extracted = :n
                WHERE textbook_id = CAST(:tid AS UUID)
            """),
            {"n": cnt, "tid": textbook_id},
        )
    log.info("  textbooks.tasks_extracted → %d", cnt)


def fetch_tasks_by_ids(engine: Engine, task_ids: list[str]) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer,
                       tm.answer_type, tm.skill_id, tm.toc_id,
                       tm.difficulty, tm.cognitive_load, tm.source_type,
                       tm.is_star, tm.task_category, tm.tags,
                       tm.distractor_meta,
                       tm.answer_options, tm.question_latex, tm.question_image_url,
                       tm.source_reference, tm.verification_status,
                       tt.paragraph_number, tt.exercise_number,
                       tt.textbook_id::text AS textbook_id
                FROM tasks_master tm
                JOIN textbook_tasks tt ON tt.task_id = tm.id
                WHERE tm.id = ANY(:ids)
                ORDER BY tm.id
            """),
            {"ids": task_ids},
        ).mappings().fetchall()
    return [dict(r) for r in rows]


def process_task_ids(engine: Engine, task_ids: list[str], dry_run: bool) -> None:
    rows = fetch_tasks_by_ids(engine, task_ids)
    log.info("task-ids: %d rows for %d ids", len(rows), len(task_ids))
    by_tb: dict[str, list[dict]] = {}
    for row in rows:
        by_tb.setdefault(row["textbook_id"], []).append(row)

    for tb_id, tb_rows in by_tb.items():
        results: list[SplitResult] = []
        for row in tb_rows:
            res = split_task(row)
            res._row = row  # type: ignore[attr-defined]
            if res.items:
                results.append(res)
                log.info("  SPLIT %s → %d items", res.original_id, len(res.items))
            else:
                log.info("  SKIP %s (%s)", row["id"], res.skip_reason or "no_subitems")
        if results:
            n_del, n_ins = apply_split(engine, tb_id, results, dry_run)
            log.info("  %s: deleted %d parents, inserted %d children", tb_id, n_del, n_ins)
            if not dry_run:
                with engine.begin() as conn:
                    cnt = conn.execute(
                        text("SELECT COUNT(*) FROM textbook_tasks WHERE textbook_id = CAST(:tid AS UUID)"),
                        {"tid": tb_id},
                    ).scalar()
                    conn.execute(
                        text("UPDATE textbooks SET tasks_extracted = :n WHERE textbook_id = CAST(:tid AS UUID)"),
                        {"n": cnt, "tid": tb_id},
                    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--textbook-ids",
        nargs="*",
        help="Subset of textbook_id prefixes (default: all in ALL_TEXTBOOKS)",
    )
    ap.add_argument(
        "--task-ids",
        nargs="*",
        help="Split only these task ids (e.g. G8_TB_21_532.4)",
    )
    ap.add_argument(
        "--tagged-only",
        action="store_true",
        help="Only tasks with needs_compound_split=true (skip heuristic-only)",
    )
    ap.add_argument(
        "--include-content-repair",
        action="store_true",
        help="Also attempt tasks already marked needs_content_repair",
    )
    ap.add_argument(
        "--no-tag-bad-splits",
        action="store_true",
        help="Do not mark rejected splits as needs_content_repair",
    )
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    if args.task_ids:
        process_task_ids(engine, list(args.task_ids), args.dry_run)
        log.info("All done.")
        return 0

    target = ALL_TEXTBOOKS
    if args.textbook_ids:
        target = {
            k: v for k, v in ALL_TEXTBOOKS.items()
            if any(k.startswith(p) for p in args.textbook_ids)
        }
        if not target:
            log.error("No matching textbooks for: %s", args.textbook_ids)
            return 1

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    log.info("split_compound_tasks [%s] — %d textbooks", mode, len(target))

    for tid, (title, _prefix) in target.items():
        process_textbook(
            engine,
            tid,
            title,
            args.dry_run,
            tagged_only=args.tagged_only,
            skip_content_repair=not args.include_content_repair,
            tag_bad_splits=not args.no_tag_bad_splits,
        )

    log.info("All done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
