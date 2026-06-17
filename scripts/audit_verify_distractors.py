#!/usr/bin/env python3
"""
Полный аудит: verify ответа (Gemini Flash) + дистракторы.

Логика:
  - Перерешать задачу, сверить с correct_answer
  - Совпало + дистракторы есть → только тег verified, дистракторы не трогаем
  - Совпало + дистракторов нет → создать
  - Ответ исправлен → старые дистракторы удаляются, новые обязательны
  - Исправлен, но Gemini не выдал дистракторы → distractor_meta=[], distractor_regen_pending
  - Mismatch (доказательство/текст) → answer_mismatch, дистракторы очищаются

Usage:
  docker exec content-worker python /app/scripts/audit_verify_distractors.py --class-level 8
  docker exec content-worker python /app/scripts/audit_verify_distractors.py --grades 5-8
  docker exec content-worker python /app/scripts/audit_verify_distractors.py \\
    --textbook-id b8f4a2c1-3d5e-4f60-9182-3456789abcde --class-level 8
"""
from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("audit_verify")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.verify_distractor_pass import fetch_tasks_for_verify, run_verify_distractor_pass


def _parse_grades(spec: str) -> tuple[int, ...]:
    if "-" in spec:
        a, b = spec.split("-", 1)
        return tuple(range(int(a), int(b) + 1))
    return (int(spec),)


def print_stats(engine, class_levels: tuple[int, ...]) -> None:
    level_sql = ", ".join(str(x) for x in class_levels)
    with engine.connect() as conn:
        row = conn.execute(text(f"""
            SELECT
              COUNT(DISTINCT tm.id) AS total,
              COUNT(DISTINCT CASE WHEN COALESCE(tm.tags->>'answer_gemini_verified','false')='true'
                THEN tm.id END) AS verified,
              COUNT(DISTINCT CASE WHEN tm.distractor_meta IS NOT NULL
                AND jsonb_array_length(tm.distractor_meta) > 0 THEN tm.id END) AS with_dist,
              COUNT(DISTINCT CASE WHEN COALESCE(tm.tags->>'distractor_regen_pending','false')='true'
                THEN tm.id END) AS regen_pending,
              COUNT(DISTINCT CASE WHEN COALESCE(tm.tags->>'answer_mismatch','false')='true'
                THEN tm.id END) AS mismatch
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level IN ({level_sql})
              AND tm.correct_answer IS NOT NULL AND trim(tm.correct_answer) != ''
        """)).fetchone()
    log.info(
        "STATS grades %s: total=%s verified=%s dist=%s regen_pending=%s mismatch=%s",
        class_levels, row[0], row[1], row[2], row[3], row[4],
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Verify answers + distractors audit")
    p.add_argument("--class-level", type=int, help="Single grade, e.g. 8")
    p.add_argument("--grades", type=str, help="Range e.g. 5-8 or single 6")
    p.add_argument("--textbook-id", type=str, default=None)
    p.add_argument("--dry-run", action="store_true", help="Count only, no API calls")
    args = p.parse_args()

    if args.grades:
        levels = _parse_grades(args.grades)
    elif args.class_level:
        levels = (args.class_level,)
    else:
        p.error("Specify --class-level or --grades")

    engine = create_engine(get_settings().database_url)
    log.info("=" * 60)
    log.info("Audit verify+distractors grades=%s textbook=%s", levels, args.textbook_id or "ALL")

    rows = fetch_tasks_for_verify(
        engine,
        class_levels=levels,
        textbook_id=args.textbook_id,
    )
    log.info("Tasks to process: %d", len(rows))
    if args.dry_run:
        print_stats(engine, levels)
        return 0

    if not rows:
        log.info("Nothing to do — all verified with distractors")
        print_stats(engine, levels)
        return 0

    stats = run_verify_distractor_pass(engine, rows, label=f"grades-{levels}")
    log.info("Done: %s", stats)
    print_stats(engine, levels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
