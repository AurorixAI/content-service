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
    "351a95c1-5208-4ae9-8323-6d7dd5e8bb82": ("Математика 6 класс — Виленкин",           "G6_TB"),
    "e8f3a1b2-7c4d-5e6f-8091-2345678abcde": ("Алгебра 8 класс — Школьное издание",     "G8_ALG"),
    "b8f4a2c1-3d5e-4f60-9182-3456789abcde": ("Алгебра 8 класс — Макарычев",            "G8_TB"),
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
    r"(?:^|[;\n|])\s*([абвг])\)\s+(.*?)(?=[;\n|]\s*[абвг]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)

_ANS_NUM_RE = re.compile(r"\d+\)\s*(.*?)(?=\s*[;,\n]\s*\d+\)|\Z)", re.DOTALL)
_ANS_LETTER_RE = re.compile(
    r"[абвг]\)\s*(.*?)(?=\s*[;,\n]\s*[абвг]\)|\Z)",
    re.DOTALL | re.IGNORECASE,
)


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


def _parse_question(qtext: str) -> tuple[str, list[str]]:
    """Numeric 1) 2) first, then letter а) б)."""
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


def _question_uses_letters(qtext: str) -> bool:
    _, letter_items = _extract_items(qtext, _ITEM_LETTER_RE, first_token="а")
    if len(letter_items) >= 2:
        return True
    _, num_items = _extract_items(qtext, _ITEM_NUM_RE, first_token="1")
    return len(num_items) < 2


def _is_mcq(question_text: str, answer_type: str, correct_answer: str) -> bool:
    header, items = _parse_question(question_text)
    letter_mode = _question_uses_letters(question_text)

    # Structured per-item answers → compound, not MCQ
    if len(items) >= 2:
        ans_parts = _parse_answers(correct_answer, letter_mode=letter_mode)
        if len(ans_parts) >= 2:
            if not _MCQ_HEADER_RE.search(question_text[:120]):
                return False
        elif not correct_answer.strip():
            if not _MCQ_HEADER_RE.search(question_text[:120]):
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


def split_task(row: dict) -> SplitResult:
    tid     = row["id"]
    qtext   = row["question_text"] or ""
    ans     = row["correct_answer"] or ""
    atype   = row["answer_type"] or "exact_number"
    parent_ex = str(row.get("exercise_number") or "").strip()

    if _is_mcq(qtext, atype, ans):
        return SplitResult(tid, [], skip_reason="MCQ")

    letter_mode = _question_uses_letters(qtext)
    header, items = _parse_question(qtext)
    if len(items) < 2:
        return SplitResult(tid, [], skip_reason="no_subitems")

    answers = _parse_answers(ans, letter_mode=letter_mode)

    split_items = []
    for i, item_text in enumerate(items, 1):
        sub_id = f"{tid}.{i}"
        if len(sub_id) > 60:
            sub_id = f"{tid[:55]}.{i}"

        if header:
            q = f"{header}\n{item_text}"
        else:
            q = item_text

        a = answers[i - 1] if i <= len(answers) else ""
        sub_ex = f"{parent_ex}.{i}" if parent_ex else str(i)

        split_items.append({
            "id":             sub_id,
            "question_text":  q.strip(),
            "correct_answer": a,
            "exercise_number": sub_ex,
        })

    return SplitResult(tid, split_items)


# ── БД ───────────────────────────────────────────────────────────────────────

def fetch_compound_tasks(engine: Engine, textbook_id: str) -> list[dict]:
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
                       tt.paragraph_number, tt.exercise_number
                FROM tasks_master tm
                JOIN textbook_tasks tt
                  ON tt.task_id = tm.id
                 AND tt.textbook_id = CAST(:tid AS UUID)
                WHERE (
                    (tm.question_text LIKE '%%1)%%' AND tm.question_text LIKE '%%2)%%')
                    OR (
                        tm.question_text ~* '(^|[;\\n|])[[:space:]]*[а-г]\\)'
                        AND tm.question_text ~* '(^|[;\\n|])[[:space:]]*[б-г]\\)'
                    )
                )
                ORDER BY tm.id
            """),
            {"tid": textbook_id},
        ).mappings().fetchall()
    return [dict(r) for r in rows]


def _child_tags(parent_tags: dict | None, original_id: str) -> dict:
    tags = dict(parent_tags or {})
    tags["split_from"] = original_id
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
                            "answer_type":         res._row["answer_type"],
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
                            "verification_status": res._row.get("verification_status") or "pending",
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


def process_textbook(engine: Engine, textbook_id: str, title: str, dry_run: bool) -> None:
    rows = fetch_compound_tasks(engine, textbook_id)
    log.info("%s: %d compound candidates", title, len(rows))

    results = []
    stats: dict[str, int] = {"split": 0, "items_total": 0}

    for row in rows:
        res = split_task(row)
        object.__setattr__(res, "_row", row)
        if res.skip_reason:
            key = res.skip_reason.lower()
            stats[key] = stats.get(key, 0) + 1
        else:
            stats["split"] += 1
            stats["items_total"] += len(res.items)
        results.append(res)

    log.info(
        "  Plan: %d to split → %d sub-tasks | %d MCQ kept | %d no-subitems",
        stats["split"], stats["items_total"], stats.get("mcq", 0), stats.get("no_subitems", 0),
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--textbook-ids",
        nargs="*",
        help="Subset of textbook_id prefixes (default: all in ALL_TEXTBOOKS)",
    )
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

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
        process_textbook(engine, tid, title, args.dry_run)

    log.info("All done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
