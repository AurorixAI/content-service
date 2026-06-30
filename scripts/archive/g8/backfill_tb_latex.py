#!/usr/bin/env python3
"""Backfill correct_answer_latex + distractor value_latex for G8 TB where display needs it."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import enrich_distractor_latex, is_prose_answer, to_answer_latex

log = logging.getLogger("backfill_tb_latex")
logging.basicConfig(level=logging.INFO, format="%(message)s")

_MATHISH = re.compile(r"[=\\^√±]|\\frac|\\sqrt|\d+/\d+")


def needs_answer_latex_backfill(ans: str, atype: str, cal: str) -> bool:
    ans = (ans or "").strip()
    if not ans or (cal or "").strip():
        return False
    if is_prose_answer(ans):
        return False
    if atype == "multiple_choice" and len(ans) <= 3 and not _MATHISH.search(ans):
        return False
    if atype == "text":
        if len(ans) > 60 and not re.search(r"\\frac|\\sqrt|\^|≥|≤|≠", ans):
            return False
        if not _MATHISH.search(ans):
            return False
    if atype == "exact_number" and re.match(r"^-?\d+([.,]\d+)?$", ans):
        return False
    latex = to_answer_latex(ans, atype)
    if not latex or latex.count("$") % 2 != 0:
        return False
    if latex == ans:
        return False
    # Long prose answers — keep plain text for display/grading.
    if atype == "text" and re.search(r"[а-яё]{15,}", latex, re.I):
        return False
    return bool("$" in latex or "\\frac" in latex or "\\sqrt" in latex)


def needs_distractor_latex(value: str, atype: str) -> bool:
    v = (value or "").strip()
    if not v or is_prose_answer(v):
        return False
    if atype == "multiple_choice" and len(v) <= 4 and not _MATHISH.search(v):
        return False
    return bool(_MATHISH.search(v))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--answers-only", action="store_true")
    ap.add_argument("--distractors-only", action="store_true")
    args = ap.parse_args()

    do_answers = not args.distractors_only
    do_distractors = not args.answers_only

    engine = create_engine(get_settings().database_url)
    ans_updated = dist_updated = 0

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, answer_type, correct_answer,
                       COALESCE(correct_answer_latex, '') AS cal,
                       distractor_meta
                FROM tasks_master
                WHERE id LIKE 'G8_TB_%'
                ORDER BY id
            """)
        ).mappings().all()

    for row in rows:
        tid = row["id"]
        atype = row["answer_type"] or ""
        ans = (row["correct_answer"] or "").strip()
        cal = (row["cal"] or "").strip()
        dmeta = list(row["distractor_meta"] or [])

        new_cal = cal
        if do_answers and needs_answer_latex_backfill(ans, atype, cal):
            new_cal = to_answer_latex(ans, atype)
            if new_cal:
                log.info("%s answer latex: %s", tid, new_cal[:80])
                ans_updated += 1

        new_dmeta = dmeta
        if do_distractors and dmeta:
            needs_enrich = any(
                isinstance(d, dict)
                and (d.get("value") or "").strip()
                and not (d.get("value_latex") or "").strip()
                and needs_distractor_latex(str(d.get("value")), atype)
                for d in dmeta
            )
            if needs_enrich:
                enriched = enrich_distractor_latex(dmeta, atype)
                if json.dumps(enriched, ensure_ascii=False) != json.dumps(dmeta, ensure_ascii=False):
                    n = sum(
                        1
                        for a, b in zip(dmeta, enriched)
                        if isinstance(a, dict)
                        and isinstance(b, dict)
                        and not (a.get("value_latex") or "").strip()
                        and (b.get("value_latex") or "").strip()
                    )
                    log.info("%s distractor latex: +%d value_latex", tid, n)
                    new_dmeta = enriched
                    dist_updated += 1

        if args.dry_run:
            continue

        if new_cal != cal or new_dmeta is not dmeta:
            with engine.begin() as conn:
                sets = []
                params: dict = {"id": tid, "dmeta": json.dumps(new_dmeta, ensure_ascii=False)}
                sets.append("distractor_meta = cast(:dmeta AS jsonb)")
                if new_cal != cal:
                    params["latex"] = new_cal
                    sets.append("correct_answer_latex = :latex")
                sets.append("updated_at = NOW()")
                conn.execute(
                    text(f"UPDATE tasks_master SET {', '.join(sets)} WHERE id = :id"),
                    params,
                )

    log.info("Done: answers=%d distractor_tasks=%d dry_run=%s", ans_updated, dist_updated, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
