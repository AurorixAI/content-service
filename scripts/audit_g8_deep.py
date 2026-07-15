#!/usr/bin/env python3
"""G8 deep quality audit — tasks, verify, distractors, gate, LaTeX (SQL + targeted gate)."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import stored_distractors_valid, validate_distractor_set

LEVEL = 8
PREFIX = "G8_"


def main() -> int:
    engine = create_engine(get_settings().database_url)

    # ── 1. Overview (pure SQL, instant) ─────────────────────────────────────
    with engine.connect() as conn:
        ov = conn.execute(
            text(
                """
            WITH g AS (
              SELECT tm.*
              FROM tasks_master tm
              JOIN textbook_toc toc ON toc.id = tm.toc_id
              JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
              WHERE tb.class_level = :level
            )
            SELECT
              count(*) AS total,
              count(*) FILTER (WHERE verification_status = 'verified') AS verified,
              count(*) FILTER (WHERE coalesce(correct_answer,'') NOT IN ('','—','-')) AS with_answer,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) >= 2) AS dist_ge2,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2) AS dist_gaps,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) = 0) AS dist_zero,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) = 1) AS dist_one,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) >= 3) AS dist_ge3,
              count(*) FILTER (WHERE coalesce(question_latex,'') != '') AS q_latex,
              count(*) FILTER (WHERE coalesce(correct_answer_latex,'') != '') AS ans_latex,
              count(*) FILTER (
                WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) >= 2
                  AND NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                    WHERE coalesce(d->>'value','') != ''
                      AND coalesce(d->>'value_latex','') = ''
                  )
              ) AS dist_latex_full,
              count(*) FILTER (WHERE tags->>'smart_verify_status' LIKE 'failed%') AS verify_failed,
              count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_human_review') AS human_review,
              count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_compound_split') AS compound_split,
              count(*) FILTER (WHERE tags->>'generated_from_scratch' = 'true') AS from_scratch,
              count(*) FILTER (WHERE tags->>'choices_complete' = 'true') AS choices_complete,
              count(*) FILTER (WHERE tags->>'distractor_regen_pending' = 'true') AS regen_pending,
              count(*) FILTER (WHERE tags->>'distractor_regen_exhausted' = 'true') AS regen_exhausted,
              count(*) FILTER (WHERE tags ? 'distractor_manual') AS distractor_manual_tag,
              count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'local_sympy') AS canon_local,
              count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'llm_fallback') AS canon_llm,
              count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'equation_solved') AS canon_eq
            FROM g
        """
            ),
            {"level": LEVEL},
        ).mappings().one()

        sv_dist = conn.execute(
            text(
                """
            SELECT coalesce(tags->>'smart_verify_status','pending') AS st, count(*) AS n
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
            GROUP BY 1 ORDER BY n DESC
        """
            ),
            {"level": LEVEL},
        ).fetchall()

        by_type = conn.execute(
            text(
                """
            SELECT answer_type,
              count(*) AS n,
              count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2) AS gaps,
              count(*) FILTER (WHERE coalesce(question_latex,'') = '') AS no_q_latex,
              count(*) FILTER (WHERE coalesce(correct_answer_latex,'') = '') AS no_a_latex
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
            GROUP BY 1 ORDER BY n DESC
        """
            ),
            {"level": LEVEL},
        ).fetchall()

        gap_rows = conn.execute(
            text(
                """
            SELECT tm.id, tm.answer_type, left(tm.correct_answer, 60) AS ans
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
              AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) < 2
            ORDER BY tm.id
        """
            ),
            {"level": LEVEL},
        ).fetchall()

        latex_gaps = conn.execute(
            text(
                """
            SELECT tm.id, tm.answer_type
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
              AND (
                coalesce(tm.question_latex,'') = ''
                OR coalesce(tm.correct_answer_latex,'') = ''
                OR (
                  jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) >= 2
                  AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(tm.distractor_meta) d
                    WHERE coalesce(d->>'value','') != ''
                      AND coalesce(d->>'value_latex','') = ''
                  )
                )
              )
            ORDER BY tm.id
        """
            ),
            {"level": LEVEL},
        ).fetchall()

    t = ov["total"] or 1
    print("=" * 70)
    print(f"G{LEVEL} DEEP AUDIT  ({PREFIX}*)")
    print("=" * 70)

    print("\n## 1. ОБЗОР")
    for k in (
        "total", "verified", "with_answer", "dist_ge2", "dist_gaps",
        "dist_zero", "dist_one", "dist_ge3", "q_latex", "ans_latex",
        "dist_latex_full", "verify_failed", "human_review", "compound_split",
        "from_scratch", "choices_complete", "regen_pending", "regen_exhausted",
        "distractor_manual_tag", "canon_local", "canon_llm", "canon_eq",
    ):
        v = ov[k]
        pct = f"  ({100 * v / t:.1f}%)" if k != "total" else ""
        print(f"  {k:24} {v}{pct}")

    print("\n## 2. SMART VERIFY STATUS")
    for st, n in sv_dist:
        print(f"  {st:28} {n:5}  ({100 * n / t:.1f}%)")

    print("\n## 3. ПО ТИПАМ ОТВЕТА")
    print(f"  {'type':20} {'total':>6} {'gaps':>6} {'no_q_tex':>9} {'no_a_tex':>9}")
    for row in by_type:
        print(f"  {row[0] or '?':20} {row[1]:6} {row[2]:6} {row[3]:9} {row[4]:9}")

    print(f"\n## 4. DIST GAPS ({len(gap_rows)})")
    if gap_rows:
        for r in gap_rows:
            print(f"  {r[0]}  [{r[1]}]  {r[2]}")
    else:
        print("  (нет)")

    print(f"\n## 5. LATEX GAPS ({len(latex_gaps)} задач с пропусками)")
    lg_by = Counter(r[1] for r in latex_gaps)
    for at, n in lg_by.most_common():
        print(f"  {at or '?':20} {n}")
    if len(latex_gaps) <= 25:
        for r in latex_gaps:
            print(f"    {r[0]}  [{r[1]}]")

    # ── 2. Gate audit: only tasks with dist>=2 ─────────────────────────────
    print("\n## 6. GATE (dist>=2) — проверка L1–L4...")
    with engine.connect() as conn:
        dist_rows = conn.execute(
            text(
                """
            SELECT tm.id, tm.answer_type, tm.question_text, tm.correct_answer,
                   tm.distractor_meta, tm.tags
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
              AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) >= 2
            ORDER BY tm.id
        """
            ),
            {"level": LEVEL},
        ).mappings().all()

    gate_ok = gate_fail = 0
    fail_by_type: Counter = Counter()
    fail_reasons: Counter = Counter()
    fail_sources: Counter = Counter()
    fail_list: list[tuple] = []

    for i, row in enumerate(dist_rows):
        if i and i % 500 == 0:
            print(f"  ... gate check {i}/{len(dist_rows)}", flush=True)
        d = row["distractor_meta"]
        if isinstance(d, str):
            d = json.loads(d)
        q = row["question_text"] or ""
        a = row["correct_answer"] or ""
        at = row["answer_type"] or ""
        if stored_distractors_valid(d, question=q, correct_answer=a, answer_type=at, min_count=2):
            gate_ok += 1
            continue
        gate_fail += 1
        fail_by_type[at or "?"] += 1
        _, rej = validate_distractor_set(
            d, question=q, correct_answer=a, answer_type=at, max_count=len(d)
        )
        for x in rej:
            fail_reasons[x.get("gate_reason", "?")] += 1
        tags = row["tags"] if isinstance(row["tags"], dict) else json.loads(row["tags"] or "{}")
        el = (d[0].get("error_logic", "") if d and isinstance(d[0], dict) else "")
        if tags.get("distractor_manual") == "dist_gaps_step1":
            src = "close_g8_dist_gaps_template"
        elif tags.get("distractor_manual"):
            src = f"manual:{tags['distractor_manual']}"
        elif str(el).startswith("Типичная ошибка при сравнении"):
            src = "deterministic_fallback"
        elif "Неравенство не доказано" in str(el):
            src = "close_g8_prose_template"
        else:
            src = "llm_or_legacy"
        fail_sources[src] += 1
        fail_list.append(
            (row["id"], at, src, [x.get("gate_reason") for x in rej], a[:50])
        )

    print(f"\n  gate_ok={gate_ok}  gate_fail={gate_fail}  checked={len(dist_rows)}")
    print(f"  fail_by_type: {dict(fail_by_type.most_common())}")
    print(f"  fail_reasons: {dict(fail_reasons.most_common())}")
    print(f"  fail_sources: {dict(fail_sources.most_common())}")
    print(f"\n  Список gate_fail ({len(fail_list)}):")
    for tid, at, src, reasons, ans in fail_list:
        print(f"    {tid}  [{at}]  {src}  {reasons}  ans={ans}")

    # ── 3. Distractor meta quality (SQL) ───────────────────────────────────
    with engine.connect() as conn:
        ped = conn.execute(
            text(
                """
            SELECT
              count(*) FILTER (
                WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) >= 2
                  AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                    WHERE length(coalesce(d->>'error_logic', d->>'explanation', '')) < 10
                  )
              ) AS short_error_logic,
              count(*) FILTER (
                WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) >= 2
                  AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                    WHERE coalesce(d->>'error_logic', d->>'explanation', '') = ''
                  )
              ) AS missing_error_logic
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id = tm.toc_id
            JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
            WHERE tb.class_level = :level
        """
            ),
            {"level": LEVEL},
        ).mappings().one()

    print("\n## 7. ПЕДАГОГИКА ДИСТРАКТОРОВ (SQL)")
    print(f"  short_error_logic (<10 симв.): {ped['short_error_logic']}")
    print(f"  missing_error_logic:           {ped['missing_error_logic']}")

    print("\n## 8. ИТОГОВЫЙ СКОР")
    score_items = [
        ("verified", ov["verified"] / t),
        ("dist_ge2", ov["dist_ge2"] / t),
        ("q_latex", ov["q_latex"] / t),
        ("ans_latex", ov["ans_latex"] / t),
        ("dist_latex_full", ov["dist_latex_full"] / t),
        ("gate_pass (dist>=2)", gate_ok / max(len(dist_rows), 1)),
    ]
    for name, pct in score_items:
        bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
        print(f"  {name:22} {pct * 100:5.1f}%  {bar}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
