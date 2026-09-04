#!/usr/bin/env python3
"""Прогон метрик качества оцифровки → строка в EVAL.md.

    python3 scripts/eval.py --class-level 8
    python3 scripts/eval.py --class-level 7 --note "после ремонта бэкслешей"
    python3 scripts/eval.py --class-level 8 --dry-run     # не писать в EVAL.md

В контейнере:
    docker exec content-worker python3 /app/scripts/eval.py --class-level 8

Метрики определены в `src/eval/metrics.py` (чистые функции, без БД).
Здесь — только доступ к `tasks_master` и запись отчёта.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in ("/app", str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from sqlalchemy import create_engine, text  # noqa: E402

from src.eval.metrics import evaluate, format_row, load_golden, missing_numbers  # noqa: E402

EVAL_MD = REPO_ROOT / "EVAL.md"

# Задачи класса + номер упражнения и параграф из моста textbook_tasks.
# LEFT JOIN — задача без записи в мосте (exam-only) не должна пропадать из счёта.
# Условие `tt.textbook_id = toc.textbook_id` обязательно: PK моста —
# (textbook_id, task_id), одна задача может числиться в нескольких учебниках,
# и без привязки к тому же учебнику джойн размножил бы строки и раздул n_tasks.
_QUERY = text("""
    SELECT
        tm.id,
        COALESCE(tt.paragraph_number::text, '')  AS paragraph,
        COALESCE(tt.exercise_number::text, '')   AS number,
        COALESCE(tm.question_text, '')           AS question_text,
        COALESCE(tm.question_latex, '')          AS question_latex,
        COALESCE(tm.correct_answer, '')          AS correct_answer,
        tm.verification_status
    FROM tasks_master tm
    JOIN textbook_toc toc ON toc.id = tm.toc_id
    JOIN textbooks tb     ON tb.textbook_id = toc.textbook_id
    LEFT JOIN textbook_tasks tt
           ON tt.task_id = tm.id AND tt.textbook_id = toc.textbook_id
    WHERE tb.class_level = :level
      AND tm.is_active = TRUE
""")


def _engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        from src.core.config import get_settings

        url = get_settings().database_url
    return create_engine(url)


def fetch_tasks(level: int) -> list[dict]:
    """Задачи класса из tasks_master в форме, которую понимают метрики."""
    with _engine().connect() as conn:
        rows = conn.execute(_QUERY, {"level": level}).mappings().all()
    return [
        {
            "id": r["id"],
            "paragraph": r["paragraph"],
            "number": r["number"],
            "question_text": r["question_text"],
            "question_latex": r["question_latex"],
            "correct_answer": r["correct_answer"],
            # колонка появится в Сессии 3 (ответы из книги vs ИИ-решатель)
            "answer_source": None,
        }
        for r in rows
    ]


def _ensure_eval_md() -> None:
    if EVAL_MD.exists():
        return
    EVAL_MD.write_text(
        "# EVAL — метрики качества оцифровки\n\n"
        "Каждая строка дописывается `scripts/eval.py`. Метрики — `src/eval/metrics.py`.\n"
        "`—` = метрика недоступна на этом этапе (не путать с измеренным нулём).\n\n"
        "| Дата | Класс | task_recall | compile_rate | numbering_gaps | latex_ned | "
        "answer_coverage | n_tasks | Примечание |\n"
        "|------|-------|-------------|--------------|----------------|-----------|"
        "-----------------|---------|------------|\n",
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--dry-run", action="store_true", help="не писать в EVAL.md")
    ap.add_argument("--show-gaps", action="store_true", help="вывести пропущенные номера")
    args = ap.parse_args()

    label = f"G{args.class_level}"

    try:
        tasks = fetch_tasks(args.class_level)
    except Exception as exc:  # noqa: BLE001 — понятное сообщение вместо трейсбека
        print(f"[eval] нет доступа к БД: {exc}", file=sys.stderr)
        print("[eval] подними PostgreSQL (docker compose up -d) или задай DATABASE_URL",
              file=sys.stderr)
        return 2

    if not tasks:
        print(f"[eval] в tasks_master нет активных задач для класса {args.class_level}",
              file=sys.stderr)
        return 1

    golden = load_golden(label)
    if not golden:
        print(f"[eval] ВНИМАНИЕ: golden-набор {label}.jsonl пуст или отсутствует — "
              "task_recall и latex_ned будут «—». См. src/eval/golden/README.md",
              file=sys.stderr)

    metrics = evaluate(tasks, golden, label)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    if args.show_gaps:
        miss = missing_numbers(tasks)
        if miss:
            print("\nПропущенные номера по параграфам:", file=sys.stderr)
            for para, nums in sorted(miss.items())[:40]:
                print(f"  §{para}: {nums}", file=sys.stderr)

    if args.dry_run:
        print("\n[eval] --dry-run: EVAL.md не тронут", file=sys.stderr)
        return 0

    _ensure_eval_md()
    with EVAL_MD.open("a", encoding="utf-8") as fh:
        fh.write(format_row(metrics, args.note) + "\n")
    print(f"\n[eval] строка дописана в {EVAL_MD}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
