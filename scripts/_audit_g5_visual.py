#!/usr/bin/env python3
"""G5 visual dependency audit: figures/tables vs attached images."""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

# Figure-required wording (from prune_no_figure + figure_links)
NEEDS_FIGURE_RE = re.compile(
    r"по рисунку|на рисунке|рисунке\s+\d+|рис\.\s*\d+|рис\.\s*[а-яё]|"
    r"изображ[её]нн[а-я]+ на рис|пользуясь графиком[^,]*рисунке|"
    r"используя график[^.]*рис\.|изображенного на рисунке|"
    r"см\.\s*рис|на чертеже|по графику|смотри рис|"
    r"(?<![а-яё])черт[её]ж(?![а-яё])|"
    r"на\s+рис\.|рисунок\s+\d|график\s+функции|координатн\w*\s+плоскост",
    re.I,
)

# Table-required wording
NEEDS_TABLE_RE = re.compile(
    r"таблиц[а-яё]*|заполните\s+таблиц|по\s+таблиц|в\s+таблиц|"
    r"данные\s+в\s+таблиц|таблиц[а-яё]*\s+показывает|составьте\s+таблиц",
    re.I,
)

# Draw-in-notebook — needs visual but offline, not attachable
DRAW_OFFLINE_RE = re.compile(
    r"начерт[иь].*тетрад|нарисуй.*тетрад|построй.*тетрад|"
    r"измерь\s+линейк|вырежи|склей",
    re.I,
)


def main() -> int:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT
              tm.id,
              tm.question_text,
              tm.task_category,
              COALESCE(tm.question_image_url, '') AS image_url,
              (SELECT COUNT(*) FROM task_figure_refs tfr WHERE tfr.task_id = tm.id) AS fig_refs,
              tb.title AS textbook
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 5
            ORDER BY tm.id
        """)).mappings().all()

    total = len(rows)
    has_image = 0
    no_image = 0

    needs_fig = []
    needs_table = []
    needs_any_visual = []
    needs_visual_no_img = []
    draw_offline = []
    with_drawing_cat = []
    compound_whole_visual = []

    seen_ids: set[str] = set()

    for r in rows:
        tid = r["id"]
        q = r["question_text"] or ""
        img = bool(r["image_url"].strip()) or (r["fig_refs"] or 0) > 0
        if img:
            has_image += 1
        else:
            no_image += 1

        fig_need = bool(NEEDS_FIGURE_RE.search(q))
        tbl_need = bool(NEEDS_TABLE_RE.search(q))
        offline_draw = bool(DRAW_OFFLINE_RE.search(q))
        cat_draw = (r["task_category"] or "") == "with_drawing"

        if fig_need:
            needs_fig.append((tid, q[:80], img))
        if tbl_need:
            needs_table.append((tid, q[:80], img))
        if fig_need or tbl_need or cat_draw:
            if tid not in seen_ids:
                seen_ids.add(tid)
                needs_any_visual.append((tid, fig_need, tbl_need, cat_draw, img, q[:70]))
        if offline_draw:
            draw_offline.append(tid)
        if cat_draw:
            with_drawing_cat.append(tid)
        if (fig_need or tbl_need) and not img and not offline_draw:
            needs_visual_no_img.append((tid, "fig" if fig_need else "tbl", q[:80]))

    # figure inventory
    with engine.connect() as c:
        fig_stats = c.execute(text("""
            SELECT
              COUNT(*) AS total_figures,
              COUNT(*) FILTER (
                WHERE COALESCE(semantic_json->>'type','') = 'data_table'
                   OR COALESCE(semantic_json->>'usefulness_reason','') = 'data_table'
              ) AS table_figures,
              COUNT(*) FILTER (WHERE image_url IS NOT NULL AND image_url <> '') AS with_png
            FROM task_figures tf
            JOIN textbooks tb ON tb.textbook_id = tf.textbook_id
            WHERE tb.class_level = 5
        """)).mappings().one()

        linked = c.execute(text("""
            SELECT COUNT(DISTINCT tm.id)
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            JOIN task_figure_refs tfr ON tfr.task_id = tm.id
            WHERE tb.class_level = 5
        """)).scalar()

        multi_ref = c.execute(text("""
            SELECT COUNT(*) FROM (
              SELECT tm.id FROM tasks_master tm
              JOIN textbook_toc toc ON toc.id = tm.toc_id
              JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
              JOIN task_figure_refs tfr ON tfr.task_id = tm.id
              WHERE tb.class_level = 5
              GROUP BY tm.id HAVING COUNT(*) > 1
            ) x
        """)).scalar()

        compound_whole = c.execute(text("""
            SELECT tm.id, tm.tags->>'compound_whole', LEFT(tm.question_text, 70)
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = 5
              AND tm.tags->>'compound_whole' IN (
                'table_fill_single', 'figure_match_prose', 'area_grid_single_answer'
              )
        """)).fetchall()

    # overlap stats
    fig_only = sum(1 for x in needs_any_visual if x[1] and not x[2])
    tbl_only = sum(1 for x in needs_any_visual if x[2] and not x[1])
    both = sum(1 for x in needs_any_visual if x[1] and x[2])
    visual_has = sum(1 for x in needs_any_visual if x[4])
    visual_missing = sum(1 for x in needs_any_visual if not x[4])

    print("=" * 60)
    print("G5 — задания с картинками / таблицами")
    print("=" * 60)
    print(f"\nВсего задач G5: {total}")
    print(f"\n--- Прикреплённый визуал (любой) ---")
    print(f"  Есть картинка (fig_refs или question_image_url): {has_image}")
    print(f"  Нет картинки: {no_image}")
    print(f"  question_image_url заполнен: 0 (колонка не используется на G5)")
    print(f"  task_figure_refs привязано: {linked} задач")
    print(f"  задач с 2+ рисунками: {multi_ref}")

    print(f"\n--- Инвентарь task_figures (G5) ---")
    print(f"  Всего фигур в БД: {fig_stats['total_figures']}")
    print(f"  С PNG (image_url): {fig_stats['with_png']}")
    print(f"  Тип data_table: {fig_stats['table_figures']}")

    print(f"\n--- По тексту вопроса (нужен визуал) ---")
    print(f"  Упоминают рисунок/график/чертёж: {len(needs_fig)}")
    print(f"    из них с картинкой: {sum(1 for _,_,h in needs_fig if h)}")
    print(f"    без картинки: {sum(1 for _,_,h in needs_fig if not h)}")
    print(f"  Упоминают таблицу: {len(needs_table)}")
    print(f"    из них с картинкой: {sum(1 for _,_,h in needs_table if h)}")
    print(f"    без картинки: {sum(1 for _,_,h in needs_table if not h)}")
    print(f"  task_category=with_drawing: {len(with_drawing_cat)}")
    print(f"  «Начерти в тетради» (оффлайн, не attach): {len(draw_offline)}")

    print(f"\n--- Объединённо (рисунок ИЛИ таблица ИЛИ with_drawing) ---")
    print(f"  Всего таких задач: {len(needs_any_visual)}")
    print(f"    только рисунок: {fig_only}")
    print(f"    только таблица: {tbl_only}")
    print(f"    оба в тексте: {both}")
    print(f"  С прикреплённым визуалом: {visual_has} ({100*visual_has/max(1,len(needs_any_visual)):.1f}%)")
    print(f"  Без визуала: {visual_missing} ({100*visual_missing/max(1,len(needs_any_visual)):.1f}%)")

    print(f"\n--- Критично: нужен визуал, но нет картинки (не оффлайн) ---")
    print(f"  Count: {len(needs_visual_no_img)}")
    for tid, kind, preview in needs_visual_no_img[:15]:
        print(f"    {tid} [{kind}] | {preview}")
    if len(needs_visual_no_img) > 15:
        print(f"    ... +{len(needs_visual_no_img)-15} ещё")

    print(f"\n--- compound_whole (визуальные, оставлены целиком) ---")
    for tid, reason, preview in compound_whole:
        print(f"  {tid} ({reason}) | {preview}")

    # by textbook
    from collections import defaultdict
    by_tb: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "has_img": 0, "need_vis": 0, "need_no_img": 0, "need_fig": 0, "need_tbl": 0}
    )
    for r in rows:
        title = (r["textbook"] or "")[:45]
        q = r["question_text"] or ""
        img = bool(r["image_url"].strip()) or (r["fig_refs"] or 0) > 0
        fig = bool(NEEDS_FIGURE_RE.search(q))
        tbl = bool(NEEDS_TABLE_RE.search(q))
        by_tb[title]["total"] += 1
        if img:
            by_tb[title]["has_img"] += 1
        if fig:
            by_tb[title]["need_fig"] += 1
        if tbl:
            by_tb[title]["need_tbl"] += 1
        if fig or tbl:
            by_tb[title]["need_vis"] += 1
            if not img:
                by_tb[title]["need_no_img"] += 1

    print(f"\n--- По учебникам ---")
    for title, d in sorted(by_tb.items(), key=lambda x: -x[1]["total"]):
        print(
            f"  {title}\n"
            f"    всего={d['total']} | с картинкой={d['has_img']} | "
            f"текст: рис={d['need_fig']} табл={d['need_tbl']} | "
            f"нужен визуал без картинки={d['need_no_img']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
