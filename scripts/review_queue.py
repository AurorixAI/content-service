#!/usr/bin/env python3
"""Очередь ручной проверки из `tasks_staging` → HTML-вьюер.

`src/viewer/build.py` собирает страницу из задач в памяти — так его зовёт
`demo_pipeline.py`. После реального прогона задачи лежат в БД, и посмотреть на
них было нечем. Этот скрипт закрывает разрыв: читает staging, восстанавливает
задачу и вердикт гейтов и отдаёт тот же вьюер.

    docker exec content-worker python /app/scripts/review_queue.py \\
        --textbook-id <uuid> --out /app/data/review.html
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from pathlib import Path

# Работает и в контейнере (/app), и из корня репозитория на хосте.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.pipeline import gates as G  # noqa: E402
from src.pipeline.db_writer import _engine  # noqa: E402
from src.pipeline.models import ExtractedTask  # noqa: E402
from src.viewer.build import build_viewer  # noqa: E402

_SQL = """
SELECT task_id, paragraph_number, exercise_number, page,
       question_text, question_latex, shared_context,
       correct_answer, answer_type, answer_options,
       answer_source, text_source, answer_source_page, confidence,
       gate_status, gate_reasons, formulas_checked, formulas_broken,
       compile_measured, skill_id, run_id
FROM tasks_staging
WHERE (:textbook_id IS NULL OR textbook_id = CAST(:textbook_id AS UUID))
  AND (:run_id      IS NULL OR run_id = :run_id)
ORDER BY paragraph_number, exercise_number
"""


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def load(textbook_id: str | None, run_id: str | None):
    tasks: list[ExtractedTask] = []
    verdicts: list[G.Verdict] = []
    with _engine().connect() as conn:
        rows = conn.execute(
            text(_SQL), {"textbook_id": textbook_id, "run_id": run_id}
        ).mappings().all()

    for r in rows:
        t = ExtractedTask(
            temp_id=r["task_id"],
            paragraph_number=r["paragraph_number"] or "",
            exercise_number=r["exercise_number"] or "",
            page=r["page"] or 0,
            question_text=r["question_text"] or "",
            question_latex=r["question_latex"] or "",
            shared_context=r["shared_context"] or "",
            answer_raw=r["correct_answer"] or "",
            answer_type=r["answer_type"] or "exact_number",
            answer_source=r["answer_source"],
            text_source=r["text_source"],
            answer_source_page=r["answer_source_page"],
            skill_id=r["skill_id"],
        )
        t.answer_options = _as_list(r["answer_options"]) or None
        t.confidence = r["confidence"] if isinstance(r["confidence"], dict) else {}

        v = G.Verdict(
            status=r["gate_status"] or G.REVIEW,
            formulas_checked=r["formulas_checked"] or 0,
            formulas_broken=r["formulas_broken"] or 0,
            compile_measured=bool(r["compile_measured"]),
        )
        v.reasons = [str(x) for x in _as_list(r["gate_reasons"])]
        tasks.append(t)
        verdicts.append(v)
    return tasks, verdicts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--textbook-id")
    ap.add_argument("--run-id")
    ap.add_argument("--out", default="/app/data/review.html")
    ap.add_argument("--title", default="Очередь ручной проверки")
    args = ap.parse_args()

    if not args.textbook_id and not args.run_id:
        print("нужен --textbook-id или --run-id", file=sys.stderr)
        return 2

    tasks, verdicts = load(args.textbook_id, args.run_id)
    if not tasks:
        print("в tasks_staging нет строк по этому фильтру", file=sys.stderr)
        return 1

    path = build_viewer(tasks, verdicts, Path(args.out), title=args.title)
    n_reject = sum(1 for v in verdicts if v.status == G.REJECT)
    n_review = sum(1 for v in verdicts if v.status == G.REVIEW)
    print(f"задач: {len(tasks)}  pass={len(tasks) - n_review - n_reject} "
          f"review={n_review} reject={n_reject}")
    print(f"→ {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
