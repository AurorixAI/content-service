#!/usr/bin/env python3
"""Professional close for G6–G8: sign-answer blockers, LaTeX gaps, final audit."""
from __future__ import annotations

import argparse
import json
import logging
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_sympy_gate import enrich_distractor_latex, to_answer_latex

log = logging.getLogger("close_grades_prof")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Lone ASCII '-' is a valid sign answer but trips no_answer heuristics.
SIGN_FIXES: dict[str, tuple[str, str]] = {
    "G7_ALG_4_3.2": ("минус", "sign_minus_textbook"),
    "G7_ALG_4_3.4": ("минус", "sign_minus_textbook"),
    "G8_TB_2_17.2": ("\u2212", "sign_negative_fraction"),
    "G8_TB_2_17.3": ("\u2212", "sign_negative_fraction"),
}

LATEX_ONLY = ("G8_TB_6_133.3",)


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def _dmeta(raw) -> list:
    if isinstance(raw, list):
        return list(raw)
    if raw in (None, "", "null"):
        return []
    return json.loads(raw)


def fix_sign_answers(engine, *, dry_run: bool) -> int:
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT id, correct_answer, answer_type, tags, distractor_meta "
                "FROM tasks_master WHERE id = ANY(:ids)"
            ),
            {"ids": list(SIGN_FIXES)},
        ).mappings().all()
    fixed = 0
    for row in rows:
        tid = row["id"]
        new_ans, reason = SIGN_FIXES[tid]
        atype = (row["answer_type"] or "text").lower()
        tags = _tags(row["tags"])
        if (row["correct_answer"] or "").strip() == new_ans:
            log.info("  skip %s (already %r)", tid, new_ans)
            continue
        tags["answer_previous"] = row["correct_answer"]
        tags["fix_grades_prof"] = reason
        tags["answer_source"] = "manual_math_review"
        tags["answer_locked"] = True
        cal = to_answer_latex(new_ans, atype)
        if dry_run:
            log.info("  [dry] %s  %r -> %r", tid, row["correct_answer"], new_ans)
            fixed += 1
            continue
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE tasks_master
                    SET correct_answer = :a,
                        correct_answer_latex = :cal,
                        tags = cast(:t AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": tid,
                    "a": new_ans,
                    "cal": cal,
                    "t": json.dumps(tags, ensure_ascii=False),
                },
            )
        log.info("  OK %s  %r -> %r", tid, row["correct_answer"], new_ans)
        fixed += 1
    return fixed


def fix_latex_gaps(engine, *, dry_run: bool) -> int:
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT id, answer_type, distractor_meta, correct_answer_latex "
                "FROM tasks_master WHERE id = ANY(:ids)"
            ),
            {"ids": list(LATEX_ONLY)},
        ).mappings().all()
    fixed = 0
    for row in rows:
        tid = row["id"]
        atype = (row["answer_type"] or "text").lower()
        dmeta = enrich_distractor_latex(_dmeta(row["distractor_meta"]), atype)
        missing = sum(
            1
            for d in dmeta
            if isinstance(d, dict)
            and (d.get("value") or "").strip()
            and not (d.get("value_latex") or "").strip()
        )
        if not missing:
            log.info("  skip %s (latex ok)", tid)
            continue
        if dry_run:
            log.info("  [dry] %s  fill %d distractor latex", tid, missing)
            fixed += 1
            continue
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE tasks_master
                    SET distractor_meta = cast(:d AS jsonb), updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": tid, "d": json.dumps(dmeta, ensure_ascii=False)},
            )
        log.info("  OK %s  distractor_latex filled (%d)", tid, missing)
        fixed += 1
    return fixed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-sign", action="store_true")
    ap.add_argument("--skip-latex", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    log.info("=== Sign-answer blockers ===")
    n_sign = 0 if args.skip_sign else fix_sign_answers(engine, dry_run=args.dry_run)
    log.info("=== LaTeX micro-gaps ===")
    n_latex = 0 if args.skip_latex else fix_latex_gaps(engine, dry_run=args.dry_run)
    log.info("Done: sign=%d latex=%d", n_sign, n_latex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
