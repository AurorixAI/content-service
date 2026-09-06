from __future__ import annotations

import argparse
import json
import os
import re

import psycopg2
import psycopg2.extras


THEORY_PROMPT_RE = re.compile(
    r"^(что называется|что такое|сформулируйте правило|какое обозначение|"
    r"какие числа образуют|какие действия всегда выполнимы|в каком виде можно представить|"
    r"как называется|чем называется|для чего|какова|какой|"
    r"сколько корней имеет|какие действия|какие числа|в каком случае)",
    re.I,
)
COMMAND_PROMPT_RE = re.compile(
    r"^(решите|найдите|вычислите|запишите|упростите|определите|докажите|"
    r"постройте|сравните|решите систему|решите неравенство|решите уравнение|"
    r"найдите множество решений|найдите длины|найдите первый член|найдите сумму|"
    r"решите задачу)\b",
    re.I,
)
PLACEHOLDER_Q_RE = re.compile(r"(не дано|нет условия|не указано|без условия|только ответ)", re.I)
ANSWER_PLACEHOLDER_RE = re.compile(r"^(невозможно определить|невозможно|нет данных|нет ответа)$", re.I)


def norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def strip_subtask_label(text: str) -> str:
    text = text.strip().rstrip(".;,")
    text = re.sub(r"^[абвгдеёжзийклмнопрстуфхцчшщa-z]\)\s*", "", text, flags=re.I)
    text = re.sub(r"^\(?[абвгдеёжзийклмнопрстуфхцчшщa-z]\)?\s*[:.]?\s*", "", text, flags=re.I)
    return text.strip().rstrip(".;,")


def task_tail(question_text: str) -> str:
    q = norm(question_text)
    if ":" in q:
        tail = q.rsplit(":", 1)[-1]
    else:
        tail = q
    return strip_subtask_label(tail)


def is_theory_prompt(question_text: str) -> bool:
    return bool(THEORY_PROMPT_RE.search(norm(question_text)))


def is_missing_condition(question_text: str) -> bool:
    return bool(PLACEHOLDER_Q_RE.search(norm(question_text)))


def is_atomic_math_snippet(text: str) -> bool:
    snippet = norm(text)
    if not snippet:
        return False
    if ANSWER_PLACEHOLDER_RE.match(snippet):
        return True
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", snippet):
        return True
    if re.fullmatch(r"[-+]?\d+/\d+", snippet):
        return True
    if re.fullmatch(r"[a-zA-Zа-яА-Я]\^\d+", snippet):
        return True
    if re.fullmatch(r"[a-zA-Zа-яА-Я]{1,3}", snippet):
        return True
    return False


def is_fragment_stub(question_text: str, correct_answer: str) -> bool:
    q = norm(question_text)
    if not COMMAND_PROMPT_RE.search(q):
        return False

    tail = task_tail(q)
    answer = norm(correct_answer)

    if is_atomic_math_snippet(tail) and len(tail) <= 12:
        return True

    if is_atomic_math_snippet(answer) and len(answer) <= 24 and len(tail) <= 20:
        return True

    return False


def classify_task(question_text: str, correct_answer: str) -> str | None:
    if is_theory_prompt(question_text):
        return None
    if is_missing_condition(question_text):
        return "type_a"
    if is_fragment_stub(question_text, correct_answer):
        return "type_b"
    return None


def fetch_tasks(cur, class_level: int):
    cur.execute(
        """
        SELECT tm.id, tm.question_text, tm.correct_answer,
               tm.answer_type,
               tm.tags->>'quarantine_v3_needs_review' AS in_hr,
               tm.tags->>'quarantine_v3_verified' AS verified
        FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = %s
        ORDER BY tm.id
        """,
        (class_level,),
    )
    return [dict(r) for r in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, default=9)
    ap.add_argument("--output", default="/app/data/garbage_report.json")
    args = ap.parse_args()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    rows = fetch_tasks(cur, args.class_level)

    ignored_theory = []
    type_a_tasks = []
    type_b_tasks = []
    clean_rows = []

    for row in rows:
        cls = classify_task(row.get("question_text"), row.get("correct_answer"))
        if cls == "type_a":
            type_a_tasks.append(row)
        elif cls == "type_b":
            type_b_tasks.append(row)
        elif is_theory_prompt(row.get("question_text")):
            ignored_theory.append(row)
        else:
            clean_rows.append(row)

    report = {
        "class_level": args.class_level,
        "ignored_theory": ignored_theory,
        "type_a": type_a_tasks,
        "type_b": type_b_tasks,
        "clean_sample_size": len(clean_rows),
        "summary": {
            "total": len(rows),
            "ignored_theory": len(ignored_theory),
            "type_a": len(type_a_tasks),
            "type_b": len(type_b_tasks),
            "clean": len(clean_rows),
        },
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"G{args.class_level} total: {len(rows)}")
    print(f"Ignored theory prompts: {len(ignored_theory)}")
    print(f"Type A (missing condition): {len(type_a_tasks)}")
    print(f"Type B (fragment stub): {len(type_b_tasks)}")
    print(f"Clean sample size: {len(clean_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
