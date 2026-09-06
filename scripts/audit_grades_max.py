#!/usr/bin/env python3
"""Maximum-detail audit for grades 6/7/8 — all queues, gaps, risks."""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings


def audit_level(level: int) -> None:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        ov = c.execute(
            text("""
                WITH g AS (
                  SELECT tm.* FROM tasks_master tm
                  JOIN textbook_toc toc ON toc.id = tm.toc_id
                  JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                  WHERE tb.class_level = :l
                )
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE verification_status = 'verified') AS verified,
                  count(*) FILTER (WHERE verification_status = 'pending') AS pending,
                  count(*) FILTER (WHERE verification_status NOT IN ('verified','pending')) AS other_status,
                  count(*) FILTER (WHERE coalesce(correct_answer,'') IN ('','—')) AS no_answer,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_human_review') AS human_review,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' LIKE 'failed%') AS verify_failed,
                  count(*) FILTER (WHERE tags->>'smart_verify_status' = 'needs_compound_split') AS compound_split,
                  count(*) FILTER (WHERE tags->>'distractor_regen_pending' = 'true') AS regen_pending,
                  count(*) FILTER (WHERE tags->>'distractor_regen_exhausted' = 'true') AS regen_exhausted,
                  count(*) FILTER (WHERE tags->>'distractor_regen_exhausted' = 'true'
                    AND jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2) AS regen_exhausted_gap,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2) AS dist_lt2,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2
                    AND answer_type NOT IN ('text','open_text','coordinate')) AS dist_lt2_nontext,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) < 2
                    AND answer_type IN ('text','open_text','coordinate')
                    AND coalesce(tags->>'choices_complete','false') != 'true') AS text_no_choices,
                  count(*) FILTER (WHERE coalesce(question_latex,'') = '') AS no_q_latex,
                  count(*) FILTER (WHERE coalesce(correct_answer_latex,'') = '') AS no_a_latex,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]')) >= 2
                    AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                      WHERE coalesce(d->>'value','') != ''
                        AND coalesce(d->>'value_latex','') = ''
                    )) AS dist_missing_latex,
                  count(*) FILTER (WHERE tags->>'answer_source' = 'manual_math_review') AS manual_math,
                  count(*) FILTER (WHERE tags->>'fix_g6_final' IS NOT NULL) AS fix_g6_final,
                  count(*) FILTER (WHERE tags->>'fix_g7_math_review' IS NOT NULL) AS fix_g7_math,
                  count(*) FILTER (WHERE tags->>'fix_g8_math_review' IS NOT NULL) AS fix_g8_math,
                  count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'local_sympy') AS canon_local,
                  count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'llm_fallback') AS canon_llm,
                  count(*) FILTER (WHERE tags->>'answer_canonical_source' = 'text_llm') AS canon_text_llm,
                  count(*) FILTER (WHERE tags->>'answer_locked' = 'true') AS answer_locked,
                  count(*) FILTER (WHERE tags->>'choices_complete' = 'true') AS choices_complete,
                  count(*) FILTER (WHERE tags ? 'smart_verify_error' AND tags->>'smart_verify_error' != '') AS has_sv_error,
                  count(*) FILTER (WHERE tags->>'needs_content_repair' = 'true') AS content_repair,
                  count(*) FILTER (WHERE tags->>'needs_compound_split' = 'true') AS needs_compound,
                  count(*) FILTER (WHERE tags->>'generated_from_scratch' = 'true') AS from_scratch,
                  count(*) FILTER (WHERE tags ? 'question_previous') AS question_fixed,
                  count(*) FILTER (WHERE tags ? 'answer_previous') AS answer_corrected
                FROM g
            """),
            {"l": level},
        ).mappings().one()

        sv = c.execute(
            text("""
                SELECT coalesce(tags->>'smart_verify_status','(none)') st, count(*) n
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l GROUP BY 1 ORDER BY n DESC
            """),
            {"l": level},
        ).fetchall()

        ver = c.execute(
            text("""
                SELECT coalesce(verification_status,'(null)') st, count(*) n
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l GROUP BY 1 ORDER BY n DESC
            """),
            {"l": level},
        ).fetchall()

        atype = c.execute(
            text("""
                SELECT answer_type, count(*) n,
                  count(*) FILTER (WHERE verification_status != 'verified') not_v,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))<2
                    AND answer_type NOT IN ('text','open_text','coordinate')) gaps
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l GROUP BY 1 ORDER BY n DESC
            """),
            {"l": level},
        ).fetchall()

        open_items = c.execute(
            text("""
                SELECT tm.id, tm.answer_type,
                  coalesce(tm.tags->>'smart_verify_status','') sv,
                  coalesce(tm.tags->>'smart_verify_error','') err,
                  coalesce(tm.tags->>'distractor_regen_pending','') rp,
                  coalesce(tm.tags->>'distractor_regen_exhausted','') re,
                  jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) nd,
                  left(tm.correct_answer,40) ans
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l AND (
                  tm.verification_status != 'verified'
                  OR tm.tags->>'smart_verify_status' = 'needs_human_review'
                  OR tm.tags->>'smart_verify_status' LIKE 'failed%'
                  OR tm.tags->>'smart_verify_status' = 'needs_compound_split'
                  OR tm.tags->>'distractor_regen_pending' = 'true'
                  OR (tm.tags->>'distractor_regen_exhausted'='true'
                      AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]'))<2)
                  OR (jsonb_array_length(COALESCE(tm.distractor_meta,'[]'))<2
                      AND tm.answer_type NOT IN ('text','open_text','coordinate'))
                  OR coalesce(tm.correct_answer,'') IN ('','—')
                  OR tm.tags->>'needs_content_repair' = 'true'
                  OR tm.tags->>'needs_compound_split' = 'true'
                )
                ORDER BY tm.id LIMIT 50
            """),
            {"l": level},
        ).mappings().all()

        latex_gaps = c.execute(
            text("""
                SELECT tm.id, tm.answer_type,
                  CASE WHEN coalesce(tm.question_latex,'')='' THEN 'q' ELSE '' END
                  || CASE WHEN coalesce(tm.correct_answer_latex,'')='' THEN 'a' ELSE '' END
                  || CASE WHEN jsonb_array_length(COALESCE(tm.distractor_meta,'[]'))>=2
                    AND EXISTS(SELECT 1 FROM jsonb_array_elements(tm.distractor_meta) d
                      WHERE coalesce(d->>'value','')!='' AND coalesce(d->>'value_latex','')='')
                    THEN 'd' ELSE '' END AS missing
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l AND (
                  coalesce(tm.question_latex,'')=''
                  OR coalesce(tm.correct_answer_latex,'')=''
                  OR (jsonb_array_length(COALESCE(tm.distractor_meta,'[]'))>=2
                    AND EXISTS(SELECT 1 FROM jsonb_array_elements(tm.distractor_meta) d
                      WHERE coalesce(d->>'value','')!='' AND coalesce(d->>'value_latex','')=''))
                )
                ORDER BY tm.id LIMIT 30
            """),
            {"l": level},
        ).mappings().all()

        pedagogy = c.execute(
            text("""
                SELECT
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))>=2) dist_ge2,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))>=2
                    AND EXISTS(SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                      WHERE length(coalesce(d->>'error_logic', d->>'explanation', '')) < 10)) short_logic,
                  count(*) FILTER (WHERE jsonb_array_length(COALESCE(distractor_meta,'[]'))>=2
                    AND EXISTS(SELECT 1 FROM jsonb_array_elements(distractor_meta) d
                      WHERE coalesce(d->>'error_logic', d->>'explanation', '') = '')) missing_logic
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l
            """),
            {"l": level},
        ).mappings().one()

        llm_risk = c.execute(
            text("""
                SELECT count(*) n FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l AND tm.verification_status='verified'
                  AND coalesce(tm.tags->>'answer_canonical_source','') IN ('llm_fallback','text_llm')
                  AND coalesce(tm.tags->>'answer_source','') != 'manual_math_review'
            """),
            {"l": level},
        ).scalar()

        stale_err = c.execute(
            text("""
                SELECT tm.id, left(tm.tags->>'smart_verify_error',60) err
                FROM tasks_master tm JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level=:l AND tm.verification_status='verified'
                  AND coalesce(tm.tags->>'smart_verify_error','') != ''
                ORDER BY tm.id LIMIT 20
            """),
            {"l": level},
        ).fetchall()

    print("=" * 70)
    print(f"G{level} MAXIMUM DETAIL AUDIT")
    print("=" * 70)
    print("\n## 1. OVERVIEW")
    for k, v in ov.items():
        pct = f" ({100*v/ov['total']:.1f}%)" if ov["total"] and k != "total" else ""
        print(f"  {k:28s} {v}{pct}")

    print("\n## 2. verification_status")
    for st, n in ver:
        flag = " <<<" if st != "verified" else ""
        print(f"  {st:30s} {n}{flag}")

    print("\n## 3. smart_verify_status")
    for st, n in sv:
        flag = " <<<" if st not in ("verified_match", "verified_corrected", "generated_from_scratch") else ""
        print(f"  {st:30s} {n}{flag}")

    print("\n## 4. BY answer_type (not_verified / real_gaps)")
    for row in atype:
        flag = ""
        if row[2] or row[3]:
            flag = f"  <<< not_v={row[2]} gaps={row[3]}"
        print(f"  {row[0] or '(null)':22s} {row[1]:5d}{flag}")

    print("\n## 5. PEDAGOGY (distractor metadata)")
    print(f"  dist_ge2:        {pedagogy['dist_ge2']}")
    print(f"  short_logic:     {pedagogy['short_logic']}")
    print(f"  missing_logic:   {pedagogy['missing_logic']}")

    print(f"\n## 6. LLM-ONLY verified (not manual_math_review): {llm_risk}")

    print(f"\n## 7. OPEN ITEMS (queues/gaps/errors) — {len(open_items)} shown")
    if open_items:
        for r in open_items:
            print(f"  {r['id']} [{r['answer_type']}] sv={r['sv']!r} nd={r['nd']} ans={r['ans']!r}")
            if r["err"]:
                print(f"    err: {r['err'][:80]}")
            if r["rp"] == "true":
                print("    regen_pending")
            if r["re"] == "true":
                print("    regen_exhausted")
    else:
        print("  (none)")

    print(f"\n## 8. LATEX GAPS — {len(latex_gaps)} shown (of {ov['no_q_latex']+ov['no_a_latex']+ov['dist_missing_latex']} total)")
    if latex_gaps:
        for r in latex_gaps[:15]:
            print(f"  {r['id']} [{r['answer_type']}] missing={r['missing']}")
        if len(latex_gaps) > 15:
            print(f"  ... +{len(latex_gaps)-15} more")
    else:
        print("  (none)")

    print(f"\n## 9. STALE smart_verify_error on verified — {len(stale_err)}")
    if stale_err:
        for tid, err in stale_err[:10]:
            print(f"  {tid}: {err}")
    else:
        print("  (none)")

    # Summary scorecard
    blockers = (
        ov["pending"] + ov["human_review"] + ov["verify_failed"] + ov["compound_split"]
        + ov["regen_pending"] + ov["regen_exhausted_gap"] + ov["dist_lt2_nontext"]
        + ov["no_answer"] + ov["content_repair"] + ov["needs_compound"]
        + (1 if ov["other_status"] else 0)
    )
    print(f"\n## 10. BLOCKERS (must-fix): {blockers}")
    print(f"## 11. QUALITY DEBT (cosmetic/optional):")
    print(f"     LaTeX gaps: q={ov['no_q_latex']} a={ov['no_a_latex']} d={ov['dist_missing_latex']}")
    print(f"     LLM-only verified: {llm_risk}")
    print(f"     missing_error_logic: {pedagogy['missing_logic']}")
    print(f"     text dist_lt2 (choices_complete): {ov['dist_lt2'] - ov['dist_lt2_nontext']}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="6,7,8")
    args = ap.parse_args()
    for lvl in [int(x) for x in args.levels.split(",")]:
        audit_level(lvl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
