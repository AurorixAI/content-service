#!/usr/bin/env python3
"""Full production audit for G5."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text
from src.core.config import get_settings

NEEDS_VIS = re.compile(
    r"рисун|рис\.|черт|график|таблиц|изображ|термометр|спидометр",
    re.I,
)


def main() -> int:
    e = create_engine(get_settings().database_url)
    s = get_settings()

    with e.connect() as c:
        # textbooks
        tbs = c.execute(text("""
            SELECT tb.title, tb.tasks_extracted,
                   (SELECT COUNT(*) FROM textbook_tasks tt WHERE tt.textbook_id = tb.textbook_id) actual,
                   (SELECT COUNT(*) FROM task_figures tf WHERE tf.textbook_id = tb.textbook_id) figs
            FROM textbooks tb WHERE tb.class_level = 5 ORDER BY tb.title
        """)).fetchall()

        ov = c.execute(text("""
            WITH g AS (
              SELECT tm.* FROM tasks_master tm
              JOIN textbook_toc toc ON toc.id = tm.toc_id
              JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
              WHERE tb.class_level = 5
            )
            SELECT
              count(*) total,
              count(*) FILTER (WHERE id LIKE '%.%') children,
              count(*) FILTER (WHERE verification_status = 'verified') verified,
              count(*) FILTER (WHERE verification_status = 'pending') pending,
              count(*) FILTER (WHERE coalesce(correct_answer,'') IN ('','—')) no_answer,
              count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_human_review') human_review,
              count(*) FILTER (WHERE tags->>'smart_verify_status' LIKE 'failed%') verify_failed,
              count(*) FILTER (WHERE tags->>'needs_compound_split' = 'true') need_compound,
              count(*) FILTER (WHERE tags->>'needs_content_repair' = 'true') content_repair,
              count(*) FILTER (WHERE tags->>'compound_whole' IS NOT NULL) compound_whole,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2
                AND answer_type NOT IN ('text','open_text','coordinate')) dist_gap,
              count(*) FILTER (WHERE coalesce(question_latex,'') = '') no_q_latex,
              count(*) FILTER (WHERE coalesce(correct_answer_latex,'') = '') no_a_latex,
              count(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM task_figure_refs tfr WHERE tfr.task_id = g.id)) has_fig,
              count(*) FILTER (WHERE NOT EXISTS (
                SELECT 1 FROM task_figure_refs tfr WHERE tfr.task_id = g.id)
                AND question_text ~* 'рисун|рис\\.|черт|график|таблиц|изображ') no_fig_no_hint,
              count(*) FILTER (WHERE coalesce(tags->>'smart_verify_status','pending') = 'pending') sv_pending
            FROM g
        """)).mappings().one()

        sv = c.execute(text("""
            SELECT coalesce(tags->>'smart_verify_status','pending') st, count(*) n
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 GROUP BY 1 ORDER BY n DESC
        """)).fetchall()

        atype = c.execute(text("""
            SELECT answer_type, count(*) n,
              count(*) FILTER (WHERE verification_status != 'verified') not_v,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))<2
                AND answer_type NOT IN ('text','open_text','coordinate')) gaps
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 GROUP BY 1 ORDER BY n DESC
        """)).fetchall()

        pedagogy = c.execute(text("""
            SELECT
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))>=2) dist_ge2,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))>=2
                AND EXISTS(SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                  WHERE coalesce(d->>'error_logic', d->>'explanation', '') = '')) missing_logic
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id WHERE tb.class_level=5
        """)).mappings().one()

        visual = c.execute(text("""
            SELECT
              count(*) FILTER (WHERE EXISTS (SELECT 1 FROM task_figure_refs tfr WHERE tfr.task_id=tm.id)) with_fig,
              count(*) FILTER (WHERE question_text ~* 'рисун|рис\\.|черт|график|таблиц|изображ'
                AND NOT EXISTS (SELECT 1 FROM task_figure_refs tfr WHERE tfr.task_id=tm.id)) need_no_fig,
              count(*) FILTER (WHERE tags->>'compound_whole' IS NOT NULL) keep_whole
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id WHERE tb.class_level=5
        """)).mappings().one()

        compound_whole = c.execute(text("""
            SELECT tm.id, tm.tags->>'compound_whole'
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 AND tm.tags->>'compound_whole' IS NOT NULL ORDER BY tm.id
        """)).fetchall()

        content_repair = c.execute(text("""
            SELECT tm.id, tm.tags->>'content_repair_reason'
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 AND tm.tags->>'needs_content_repair'='true' ORDER BY tm.id
        """)).fetchall()

        failed = c.execute(text("""
            SELECT tm.id, tm.answer_type, tm.tags->>'smart_verify_status' sv,
                   left(tm.tags->>'smart_verify_error',70) err
            FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 AND tm.tags->>'smart_verify_status' LIKE 'failed%'
            ORDER BY tm.id
        """)).fetchall()

        human = c.execute(text("""
            SELECT count(*) FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 AND tm.tags->>'smart_verify_status'='needs_human_review'
        """)).scalar()

        orphan_tt = c.execute(text("""
            SELECT count(*) FROM textbook_tasks tt JOIN textbooks tb ON tb.textbook_id=tt.textbook_id
            WHERE tb.class_level=5 AND NOT EXISTS (SELECT 1 FROM tasks_master tm WHERE tm.id=tt.task_id)
        """)).scalar()

        orphan_tm = c.execute(text("""
            SELECT count(*) FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE tb.class_level=5 AND NOT EXISTS (
              SELECT 1 FROM textbook_tasks tt WHERE tt.task_id=tm.id AND tt.textbook_id=tb.textbook_id)
        """)).scalar()

        fig_png = c.execute(text("""
            SELECT tf.figure_id, tf.textbook_id::text FROM task_figures tf
            JOIN textbooks tb ON tb.textbook_id=tf.textbook_id WHERE tb.class_level=5
        """)).fetchall()

    png_ok = png_miss = 0
    for fid, tb in fig_png:
        if (Path(s.figures_dir) / tb / f"{fid}.png").exists():
            png_ok += 1
        else:
            png_miss += 1

  # print report
    print("=" * 72)
    print("G5 — ПОЛНЫЙ АУДИТ")
    print("=" * 72)

    print("\n## 1. УЧЕБНИКИ")
    for title, extracted, actual, figs in tbs:
        sync = "OK" if extracted == actual else "MISMATCH"
        print(f"  {title[:50]}")
        print(f"    tasks: {actual} (counter={extracted}) {sync} | figures DB: {figs}")

    print("\n## 2. ОБЗОР")
    for k, v in ov.items():
        pct = f" ({100*v/ov['total']:.1f}%)" if ov['total'] and k != 'total' else ""
        print(f"  {k:22s} {v}{pct}")

    print("\n## 3. smart_verify_status")
    for st, n in sv:
        flag = " <<<" if st not in ("verified_match", "verified_corrected") else ""
        print(f"  {st:28s} {n}{flag}")

    print("\n## 4. answer_type (not_verified / dist_gaps)")
    for at, n, nv, gaps in atype:
        flag = f"  <<< not_v={nv} gaps={gaps}" if nv or gaps else ""
        print(f"  {at:22s} {n:5d}{flag}")

    print("\n## 5. ВИЗУАЛ / КАРТИНКИ")
    print(f"  tasks with figure refs:     {visual['with_fig']}")
    print(f"  need visual, no fig (text): {visual['need_no_fig']} (should be 0 after prune)")
    print(f"  compound_whole:             {visual['keep_whole']}")
    print(f"  figures in DB:              {len(fig_png)}")
    print(f"  PNG on disk:                {png_ok} ok, {png_miss} missing")
    if compound_whole:
        for tid, reason in compound_whole:
            print(f"    {tid}: {reason}")

    print("\n## 6. ДИСТРАКТОРЫ")
    print(f"  dist >= 2:        {pedagogy['dist_ge2']}")
    print(f"  missing_logic:    {pedagogy['missing_logic']}")
    print(f"  dist_gap (non-text): {ov['dist_gap']}")

    print("\n## 7. LaTeX")
    print(f"  no question_latex: {ov['no_q_latex']}")
    print(f"  no answer_latex:   {ov['no_a_latex']}")

    print("\n## 8. ЦЕЛОСТНОСТЬ")
    print(f"  orphan textbook_tasks: {orphan_tt}")
    print(f"  master без textbook_tasks: {orphan_tm}")

    print(f"\n## 9. ОЧЕРЕДИ")
    print(f"  smart_verify pending:  {ov['sv_pending']}")
    print(f"  needs_human_review:    {human}")
    print(f"  verify_failed:         {ov['verify_failed']}")
    if failed:
        for row in failed:
            print(f"    {row[0]} [{row[1]}] {row[2]} | {row[3]}")
    print(f"  needs_compound_split:  {ov['need_compound']}")
    print(f"  needs_content_repair:  {ov['content_repair']}")
    if content_repair:
        for tid, reason in content_repair[:10]:
            print(f"    {tid}: {(reason or '')[:70]}")
        if len(content_repair) > 10:
            print(f"    ... +{len(content_repair)-10}")

    blockers = (
        ov['pending'] + ov['human_review'] + ov['verify_failed']
        + ov['need_compound'] + ov['content_repair'] + ov['dist_gap']
        + ov['no_answer'] + ov['sv_pending']
    )
    cosmetic = ov['no_q_latex'] + ov['no_a_latex'] + pedagogy['missing_logic']

    print("\n" + "=" * 72)
    print("ИТОГ")
    print("=" * 72)
    print(f"  BLOCKERS (пайплайн):     ~{blockers}")
    print(f"  COSMETIC (LaTeX/logic):  ~{cosmetic}")
    print(f"  PRODUCTION READY:        НЕТ — нужен smart_verify на {ov['sv_pending']} pending")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
