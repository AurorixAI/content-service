#!/usr/bin/env python3
"""Мониторинг прогресса оцифровки + полный отчёт из БД по завершению.

Запуск внутри контейнера:
    docker exec content-worker python /app/scripts/report_job.py <job_id> [--watch]

--watch  : опрашивает каждые 30 с и печатает отчёт по мере появления параграфов.
Без флага: разово печатает текущее состояние.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

sys.path.insert(0, "/app")

from sqlalchemy import text

from src.core.job_state import JobStateManager
from src.pipeline.db_writer import _engine  # internal helper


def _q(sql: str, params: dict | None = None) -> list[dict]:
    engine = _engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params or {})
        keys = list(rows.keys())
        return [dict(zip(keys, r)) for r in rows]


def report(job_id: str) -> None:
    state = JobStateManager()
    job = state.get(job_id)
    if not job:
        print(f"[ERROR] Job not found: {job_id}")
        return

    tb_id = job["textbook_id"]
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # ── job progress ──────────────────────────────────────────────────────────
    total = job.get("paragraphs_total") or 0
    done  = job.get("paragraphs_done") or 0
    pct   = round(done / total * 100, 1) if total else 0.0

    print()
    print("=" * 70)
    print(f"  ОТЧЁТ ОБ ОЦИФРОВКЕ  [{now}]")
    print("=" * 70)
    print(f"  job_id       : {job_id}")
    print(f"  textbook_id  : {tb_id}")
    print(f"  Статус       : {job.get('status','?')}  (шаг: {job.get('step','?')})")
    print(f"  Прогресс     : {done}/{total} параграфов ({pct}%)")
    if job.get("error"):
        print(f"  ОШИБКА       : {job['error'][:200]}")

    # ── textbook info ─────────────────────────────────────────────────────────
    tb_rows = _q(
        "SELECT title, class_level, total_pages, tasks_extracted, "
        "       figures_skipped, digitization_status "
        "FROM textbooks WHERE textbook_id = CAST(:id AS UUID)",
        {"id": tb_id},
    )
    if not tb_rows:
        print("\n  [WARNING] Учебник не найден в БД")
        return
    tb = tb_rows[0]
    print()
    print(f"  Учебник      : {tb['title']}")
    print(f"  Класс        : {tb['class_level']}")
    print(f"  Страниц      : {tb['total_pages']}")
    print(f"  Задач всего  : {tb['tasks_extracted']}")
    print(f"  Рис. пропущено: {tb['figures_skipped']}")

    # ── TOC ───────────────────────────────────────────────────────────────────
    toc_rows = _q(
        "SELECT level, COUNT(*) AS cnt FROM textbook_toc "
        "WHERE textbook_id = CAST(:id AS UUID) GROUP BY level ORDER BY level",
        {"id": tb_id},
    )
    if toc_rows:
        toc_str = "  ".join(f"L{r['level']}={r['cnt']}" for r in toc_rows)
        print(f"  TOC записей  : {sum(r['cnt'] for r in toc_rows)}  ({toc_str})")

    # ── tasks breakdown ───────────────────────────────────────────────────────
    tasks = _q(
        """
        SELECT
            tm.difficulty,
            tm.task_category,
            tm.is_star,
            tm.answer_type,
            COUNT(*) AS cnt,
            ROUND(AVG(tm.irt_difficulty)::numeric, 2) AS avg_irt
        FROM tasks_master tm
        JOIN textbook_tasks tt ON tt.task_id = tm.id
        WHERE tt.textbook_id = CAST(:id AS UUID)
        GROUP BY tm.difficulty, tm.task_category, tm.is_star, tm.answer_type
        ORDER BY tm.difficulty, tm.task_category
        """,
        {"id": tb_id},
    )

    if not tasks:
        print()
        print("  Задачи ещё не записаны в БД")
    else:
        total_tasks = sum(r["cnt"] for r in tasks)
        star_tasks  = sum(r["cnt"] for r in tasks if r["is_star"])
        print()
        print(f"  ┌─ ЗАДАЧИ ({total_tasks} шт.) {'─' * 45}")

        # By difficulty
        diff_map: dict[str, int] = {}
        for r in tasks:
            diff_map[r["difficulty"]] = diff_map.get(r["difficulty"], 0) + r["cnt"]
        diff_str = "  ".join(f"{k}={v}" for k, v in sorted(diff_map.items()))
        print(f"  │  Сложность    : {diff_str}")

        # By category
        cat_map: dict[str, int] = {}
        for r in tasks:
            cat_map[r["task_category"]] = cat_map.get(r["task_category"], 0) + r["cnt"]
        for cat, cnt in sorted(cat_map.items(), key=lambda x: -x[1]):
            bar = "█" * min(30, round(cnt / total_tasks * 30))
            print(f"  │  {cat:<15}: {cnt:>5}  {bar}")

        # Star
        print(f"  │  Звёздных (★) : {star_tasks} ({round(star_tasks/total_tasks*100,1)}%)")

        # By answer type
        at_map: dict[str, int] = {}
        for r in tasks:
            at_map[r["answer_type"]] = at_map.get(r["answer_type"], 0) + r["cnt"]
        at_str = "  ".join(f"{k}={v}" for k, v in sorted(at_map.items(), key=lambda x: -x[1]))
        print(f"  │  Тип ответа   : {at_str}")

        # IRT range
        all_irt = [r["avg_irt"] for r in tasks if r["avg_irt"] is not None]
        if all_irt:
            print(f"  │  IRT (avg)    : min={min(all_irt):.2f}  max={max(all_irt):.2f}")

        print(f"  └{'─' * 55}")

    # ── figures ───────────────────────────────────────────────────────────────
    figs = _q(
        "SELECT COUNT(*) AS cnt FROM task_figures WHERE textbook_id = CAST(:id AS UUID)",
        {"id": tb_id},
    )
    fig_cnt = figs[0]["cnt"] if figs else 0

    fig_useful = _q(
        """
        SELECT
            f.semantic_json->>'is_useful' AS useful,
            COUNT(*) AS cnt
        FROM task_figures f
        WHERE f.textbook_id = CAST(:id AS UUID)
        GROUP BY useful
        """,
        {"id": tb_id},
    )
    if fig_useful:
        fu_str = "  ".join(f"{r['useful']}={r['cnt']}" for r in fig_useful)
        print(f"  Рисунки в БД   : {fig_cnt}  ({fu_str})")
    else:
        print(f"  Рисунки в БД   : {fig_cnt}")

    # ── per-chapter breakdown ─────────────────────────────────────────────────
    chapters = _q(
        """
        SELECT t.number, t.title, t.page_start, t.page_end,
               COUNT(DISTINCT tt.task_id) AS tasks_cnt
        FROM textbook_toc t
        LEFT JOIN textbook_toc child
            ON child.textbook_id = t.textbook_id AND child.parent_id = t.id
        LEFT JOIN tasks_master tm ON tm.toc_id = child.id OR tm.toc_id = t.id
        LEFT JOIN textbook_tasks tt
            ON tt.task_id = tm.id AND tt.textbook_id = t.textbook_id
        WHERE t.textbook_id = CAST(:id AS UUID)
          AND t.level = 1
        GROUP BY t.id, t.number, t.title, t.page_start, t.page_end, t.sort_order
        ORDER BY t.sort_order
        """,
        {"id": tb_id},
    )
    if chapters:
        print()
        print("  ┌─ ПО ГЛАВАМ " + "─" * 55)
        for ch in chapters:
            pages = f"стр.{ch['page_start']}–{ch['page_end']}" if ch["page_start"] else "?"
            bar = "█" * ch["tasks_cnt"] if ch["tasks_cnt"] < 50 else "█" * 49 + "…"
            print(f"  │  [{ch['number']}] {ch['title'][:35]:<35} {pages:<14} {ch['tasks_cnt']:>4} задач")
        print(f"  └{'─' * 67}")

    # ── skipped tasks (from job state) ────────────────────────────────────────
    skipped = _q(
        "SELECT tasks_skipped, figures_skipped FROM textbooks "
        "WHERE textbook_id = CAST(:id AS UUID)",
        {"id": tb_id},
    )
    if skipped and skipped[0].get("tasks_skipped"):
        print(f"\n  Пропущено задач (offline/no-answer): {skipped[0]['tasks_skipped']}")

    print()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("job_id")
    p.add_argument("--watch", action="store_true",
                   help="Опрашивать каждые 30 с до завершения")
    p.add_argument("--interval", type=int, default=30)
    args = p.parse_args()

    if not args.watch:
        report(args.job_id)
        return 0

    print(f"Мониторинг job {args.job_id} (Ctrl+C для выхода)...")
    last_done = -1
    while True:
        state = JobStateManager()
        job = state.get(args.job_id)
        if not job:
            print("Job not found"); return 1

        cur_done = job.get("paragraphs_done", 0) or 0
        status   = job.get("status", "")

        if cur_done != last_done or status in ("done", "failed"):
            report(args.job_id)
            last_done = cur_done

        if status in ("done", "failed"):
            print(f"Job finished with status: {status}")
            return 0 if status == "done" else 1

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
