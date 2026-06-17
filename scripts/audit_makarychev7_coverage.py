#!/usr/bin/env python3
"""Full coverage audit for Makarychev G7 digitization."""
from __future__ import annotations

import sys

sys.path.insert(0, "/app" if "/app" in sys.path[0:1] else ".")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.makarychev7_exercise_ranges import MAKARYCHEV7_EXERCISE_RANGES

TEXTBOOK_ID = "69fc47e1-7f72-4e79-9bf4-9ee6fb7e9b7f"


def main() -> int:
    engine = create_engine(get_settings().database_url)

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT tt.paragraph_number::int AS p,
                       array_agg(tt.exercise_number::int ORDER BY tt.exercise_number::int) AS exs
                FROM textbook_tasks tt
                WHERE tt.textbook_id = CAST(:tid AS UUID)
                GROUP BY tt.paragraph_number::int
                ORDER BY p
            """),
            {"tid": TEXTBOOK_ID},
        ).fetchall()
        db = {r.p: set(r.exs) for r in rows}

        tasks_skipped = conn.execute(
            text(
                "SELECT tasks_skipped, figures_skipped FROM textbooks "
                "WHERE textbook_id = CAST(:tid AS UUID)"
            ),
            {"tid": TEXTBOOK_ID},
        ).fetchone()

        integrity = conn.execute(
            text("""
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE tm.toc_id IS NULL) AS no_toc,
                  count(*) FILTER (WHERE trim(coalesce(tm.question_text, '')) = '') AS no_text,
                  count(*) FILTER (WHERE tm.id NOT LIKE 'G7_TB_%') AS bad_id,
                  count(*) FILTER (
                    WHERE tt_toc.number IS NOT NULL
                      AND tt_toc.number::text <> tt.paragraph_number
                  ) AS toc_mismatch
                FROM textbook_tasks tt
                JOIN tasks_master tm ON tm.id = tt.task_id
                LEFT JOIN textbook_toc tt_toc ON tt_toc.id = tm.toc_id
                WHERE tt.textbook_id = CAST(:tid AS UUID)
            """),
            {"tid": TEXTBOOK_ID},
        ).fetchone()

        skills = conn.execute(
            text("""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE cnt > 0) AS with_tasks,
                       count(*) FILTER (WHERE cnt = 0) AS no_tasks
                FROM (
                  SELECT kh.id, count(tm.id) AS cnt
                  FROM knowledge_hierarchy kh
                  LEFT JOIN tasks_master tm ON tm.skill_id = kh.id
                  WHERE kh.level = 'L4' AND kh.id LIKE 'G7_%'
                  GROUP BY kh.id
                ) s
            """)
        ).fetchone()

        diff = conn.execute(
            text("""
                SELECT tm.difficulty, tm.source_type, count(*)
                FROM tasks_master tm
                WHERE tm.skill_id LIKE 'G7_%' OR tm.id LIKE 'G7_TB_%'
                GROUP BY tm.difficulty, tm.source_type
                ORDER BY 2, 1
            """)
        ).fetchall()

        no_skill = conn.execute(
            text("""
                SELECT count(*) FROM textbook_tasks tt
                JOIN tasks_master tm ON tm.id = tt.task_id
                WHERE tt.textbook_id = CAST(:tid AS UUID) AND tm.skill_id IS NULL
            """),
            {"tid": TEXTBOOK_ID},
        ).scalar()

        toc_rows = conn.execute(
            text("""
                SELECT t.number::int AS p, t.page_start, t.page_end, t.title,
                       count(tt.task_id) AS tasks
                FROM textbook_toc t
                LEFT JOIN tasks_master tm ON tm.toc_id = t.id
                LEFT JOIN textbook_tasks tt ON tt.task_id = tm.id
                    AND tt.textbook_id = CAST(:tid AS UUID)
                WHERE t.textbook_id = CAST(:tid AS UUID) AND t.level = 2
                GROUP BY t.number, t.page_start, t.page_end, t.title, t.sort_order
                ORDER BY t.sort_order
            """),
            {"tid": TEXTBOOK_ID},
        ).fetchall()

    print("=" * 76)
    print("  АУДИТ G7 MAKARYCHEV — ПОКРЫТИЕ УПРАЖНЕНИЙ")
    print("=" * 76)
    print(f"  textbook_id: {TEXTBOOK_ID}")
    if tasks_skipped:
        print(f"  offline skipped (counter): {tasks_skipped.tasks_skipped}")
        print(f"  figures skipped: {tasks_skipped.figures_skipped}")
    print()

    total_expected = 0
    total_in_db = 0
    empty_paras: list[int] = []
    partial_paras: list[int] = []
    full_paras: list[int] = []
    para_details: list[tuple[int, int, int, float, list[int]]] = []

    print(f"{'§':>3} {'ожид':>5} {'БД':>4} {'%':>6}  пропуски")
    print("-" * 76)

    for p in range(1, 47):
        lo, hi = MAKARYCHEV7_EXERCISE_RANGES[p]
        expected = set(range(lo, hi + 1))
        in_db = db.get(p, set())
        missing = sorted(expected - in_db)
        n_exp = len(expected)
        n_db = len(in_db)
        pct = 100.0 * n_db / n_exp if n_exp else 0.0
        total_expected += n_exp
        total_in_db += n_db

        if n_db == 0:
            empty_paras.append(p)
        elif not missing:
            full_paras.append(p)
        else:
            partial_paras.append(p)
        para_details.append((p, n_exp, n_db, pct, missing))

        miss_str = ", ".join(map(str, missing[:10]))
        if len(missing) > 10:
            miss_str += f"... (+{len(missing) - 10})"
        if not missing:
            miss_str = "—"
        print(f"{p:3d} {n_exp:5d} {n_db:4d} {pct:5.1f}%  {miss_str}")

    total_missing = total_expected - total_in_db
    print("-" * 76)
    print(
        f"  ИТОГО: ожид {total_expected} | в БД {total_in_db} | "
        f"пропуск {total_missing} ({100 * total_missing / total_expected:.1f}%)"
    )
    print(f"  Полных §: {len(full_paras)} | Частичных: {len(partial_paras)} | Пустых: {len(empty_paras)}")
    print(f"  ПУСТЫЕ §: {empty_paras}")

    print("\n  ХУДШИЕ § (по % покрытия):")
    worst = sorted(para_details, key=lambda x: x[3])[:20]
    for p, n_exp, n_db, pct, missing in worst:
        if n_db == 0:
            continue
        print(f"    §{p}: {n_db}/{n_exp} ({pct:.0f}%) — нет: {missing[:6]}{'...' if len(missing)>6 else ''}")

    print("\n" + "=" * 76)
    print("  TOC × ЗАДАЧИ")
    print("=" * 76)
    print(f"{'§':>3} {'pages':>10} {'tasks':>5}  title")
    print("-" * 76)
    for r in toc_rows:
        pe = r.page_end if r.page_end is not None else "?"
        flag = " *** ПУСТО" if r.tasks == 0 else ""
        title = (r.title or "")[:38]
        print(f"{r.p:3d} {r.page_start}-{pe!s:<4} {r.tasks:5d}  {title}{flag}")

    print("\n" + "=" * 76)
    print("  ЦЕЛОСТНОСТЬ ЗАПИСИ")
    print("=" * 76)
    print(f"  Всего textbook tasks: {integrity.total}")
    print(f"  Без toc_id: {integrity.no_toc}")
    print(f"  Без текста: {integrity.no_text}")
    print(f"  Неверный id: {integrity.bad_id}")
    print(f"  toc_id ≠ §: {integrity.toc_mismatch}")
    print(f"  Без skill_id: {no_skill}")

    print("\n" + "=" * 76)
    print("  НАВЫКИ G7 (L4)")
    print("=" * 76)
    print(f"  Всего: {skills.total} | с задачами: {skills.with_tasks} | без задач: {skills.no_tasks}")
    print("  По difficulty / source:")
    for r in diff:
        print(f"    {(r.source_type or 'null'):15s} {r.difficulty}: {r.count}")

    print("\n" + "=" * 76)
    print("  РЕКОМЕНДАЦИЯ: ДОЗАПУСК")
    print("=" * 76)
    rerun = sorted(set(empty_paras + [p for p, _, n_db, pct, _ in para_details if n_db > 0 and pct < 80]))
    print(f"  § на повтор ({len(rerun)}): {rerun}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
