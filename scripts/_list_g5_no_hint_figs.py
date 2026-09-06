#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings

e = create_engine(get_settings().database_url)
with e.connect() as c:
    rows = c.execute(text("""
        SELECT tm.id, LEFT(tm.question_text, 130) AS q,
               array_agg(tf.figure_id ORDER BY tfr.order_idx) AS figs,
               array_agg(tf.page ORDER BY tfr.order_idx) AS pages,
               array_agg(LEFT(COALESCE(tf.alt_text, ''), 70) ORDER BY tfr.order_idx) AS alts,
               tb.title
        FROM tasks_master tm
        JOIN task_figure_refs tfr ON tfr.task_id = tm.id
        JOIN task_figures tf ON tf.figure_id = tfr.figure_id
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
        WHERE tb.class_level = 5
        GROUP BY tm.id, tm.question_text, tb.title
        HAVING NOT (tm.question_text ~* 'рисун|рис\\.|черт|график|таблиц|изображ')
        ORDER BY tm.id
    """)).fetchall()

print(f"count: {len(rows)}\n")
for tid, q, figs, pages, alts, title in rows:
    print(f"{tid} | {title[:30]}")
    print(f"  figs={figs} pages={pages}")
    print(f"  Q: {q}")
    if any(alts):
        print(f"  alt: {alts}")
    print()
