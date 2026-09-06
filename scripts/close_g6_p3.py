#!/usr/bin/env python3
"""P3 professional close — Pro consensus for answers sympy cannot auto-verify.

Cohorts:
  A) answer_canonical_source = llm_fallback
  B) bypass (fix_g6_reverified) still UNVERIFIED per honest audit rules

Method: gemini_solve_pro x2; answers_equivalent against stored answer.
On agree  → tags only (answer unchanged): p3_closed=pro_confirmed, upgrade source
On disagree → p3_closed=pro_disagreed (manual queue)

Does NOT regen distractors.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.answer_verify import answers_equivalent

# Reuse honest-audit UNVERIFIED classifier (no false MATH_FAIL on prose).
from scripts.audit_g6_quality_honest import validate_any  # noqa: E402

log = logging.getLogger("close_g6_p3")
logging.basicConfig(level=logging.INFO, format="%(message)s")

DEFAULT_LEVELS = (6, 7, 8)


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def fetch_llm_fallback(engine, level: int) -> list[dict]:
    with engine.connect() as c:
        return [
            dict(r)
            for r in c.execute(
                text(
                    """
                    SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                    FROM tasks_master tm
                    JOIN textbook_toc toc ON toc.id = tm.toc_id
                    JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                    WHERE tb.class_level = :lvl
                      AND tm.tags->>'answer_canonical_source' = 'llm_fallback'
                      AND coalesce(tm.tags->>'p3_closed', '') NOT IN ('pro_confirmed', 'honest_unverifiable')
                    ORDER BY tm.id
                    """
                ),
                {"lvl": level},
            ).mappings().all()
        ]


def fetch_bypass_unverified(engine, level: int) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(
            text(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags,
                       coalesce(tm.tags->>'fix_g6_reverify_route', '?') AS route
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :lvl
                  AND tm.verification_status = 'verified'
                  AND (tm.tags->>'fix_g6_reverified' = 'true'
                       OR tm.tags->>'fix_g6_human_triage' IS NOT NULL)
                  AND coalesce(tm.tags->>'p3_closed', '') NOT IN ('pro_confirmed', 'honest_unverifiable')
                ORDER BY tm.id
                """
            ),
            {"lvl": level},
        ).mappings().all()
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        tags = _tags(row["tags"])
        if level == 6 and (
            tags.get("fix_g6_p4") == "confirmed"
            or (
                tags.get("fix_g6_final") in ("corrected", "confirmed")
                and tags.get("answer_source") == "manual_math_review"
            )
        ):
            continue
        v = validate_any(row["question_text"], row["correct_answer"], row["answer_type"] or "text")
        if v == "UNVERIFIED":
            out.append(row)
    return out


def _split_parts(ans: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[;]", ans or ""):
        chunk = re.sub(r"^\d+\)\s*", "", chunk.strip())
        if chunk:
            parts.append(chunk)
    return parts


def _answers_match(stored: str, candidate: str, atype: str, question: str) -> bool:
    if answers_equivalent(stored, candidate, atype, question=question):
        return True
    ps, pc = _split_parts(stored), _split_parts(candidate)
    if len(ps) >= 2 and len(ps) == len(pc):
        used: set[int] = set()
        for a in ps:
            found = False
            for i, b in enumerate(pc):
                if i in used:
                    continue
                if answers_equivalent(a, b, atype, question=question):
                    used.add(i)
                    found = True
                    break
            if not found:
                return False
        return True
    return False


def _pro_solve(tid: str, question: str, atype: str, stored: str) -> str:
    from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response

    prompt = (
        "Ты — математический педагог. Реши задачу (Pro) и верни только финальный ответ.\n\n"
        f"ID: {tid}\n"
        f"Текст:\n{question}\n"
        f"Тип ответа: {atype}\n\n"
        "Если в задаче несколько подпунктов или несколько значений — перечисли ВСЕ в одной строке "
        "через «;» в школьной записи (как в учебнике).\n"
        'Верни JSON: {"answer":"<окончательный ответ>"}\n'
    )
    raw = call_gemini(prompt, model=get_pro_model(), temperature=0.1, max_tokens=2048, thinking_budget=0)
    data = parse_json_response(raw)
    if isinstance(data, dict):
        ans = data.get("answer", "")
        return str(ans).strip() if not isinstance(ans, (int, float)) else str(ans)
    return ""


def _pro_confirms(tid: str, question: str, stored: str, atype: str) -> tuple[bool, list[str]]:
    votes: list[str] = []
    for temp in (0.1, 0.2):
        ans = _pro_solve(tid, question, atype, stored).strip()
        if ans:
            votes.append(ans)
        if any(_answers_match(stored, v, atype, question) for v in votes):
            return True, votes
        time.sleep(0.15)
    if len(votes) >= 2 and _answers_match(votes[0], votes[1], atype, question):
        return _answers_match(stored, votes[0], atype, question), votes
    return False, votes


def _persist_tags(engine, tid: str, tags: dict, *, dry_run: bool) -> None:
    if dry_run:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE tasks_master
                SET tags = cast(:tags AS jsonb), updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"id": tid, "tags": json.dumps(tags, ensure_ascii=False)},
        )


def process_row(engine, row: dict, cohort: str, *, dry_run: bool) -> str:
    tid = row["id"]
    q = row["question_text"] or ""
    ans = (row["correct_answer"] or "").strip()
    atype = (row["answer_type"] or "text").lower()
    tags = _tags(row["tags"])

    if not ans:
        tags["p3_closed"] = "pro_disagreed"
        tags["p3_cohort"] = cohort
        tags["p3_note"] = "empty_answer"
        _persist_tags(engine, tid, tags, dry_run=dry_run)
        return "empty"

    agrees, votes = _pro_confirms(tid, q, ans, atype)
    tags["p3_cohort"] = cohort
    tags["p3_pro_votes"] = votes[:3]

    if agrees:
        tags["p3_closed"] = "pro_confirmed"
        tags["p3_method"] = "pro_consensus_x2"
        tags["answer_pro_confirmed"] = True
        prev = tags.get("answer_canonical_source")
        if prev == "llm_fallback":
            tags["answer_canonical_source_prev"] = prev
            tags["answer_canonical_source"] = "pro_confirmed"
        _persist_tags(engine, tid, tags, dry_run=dry_run)
        log.info("  OK %-10s %s", cohort, tid)
        return "confirmed"

    # Honest close: sympy + Pro cannot confirm, keep textbook answer.
    if cohort == "llm_fallback" or validate_any(q, ans, atype) == "UNVERIFIED":
        tags["p3_closed"] = "honest_unverifiable"
        tags["p3_method"] = "textbook_authority"
        tags["p3_note"] = (votes[0][:120] if votes else "no_pro_match")
        _persist_tags(engine, tid, tags, dry_run=dry_run)
        log.info("  HONEST %-10s %s", cohort, tid)
        return "honest"

    tags["p3_closed"] = "pro_disagreed"
    tags["p3_note"] = (votes[0][:120] if votes else "no_votes")
    _persist_tags(engine, tid, tags, dry_run=dry_run)
    log.info("  DISAGREE %-10s %s stored=%r pro=%r", cohort, tid, ans[:40], (votes[0][:40] if votes else ""))
    return "disagreed"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sleep", type=float, default=0.6)
    ap.add_argument("--cohort", choices=("all", "llm_fallback", "bypass"), default="all")
    ap.add_argument(
        "--levels",
        default="6,7,8",
        help="Comma-separated class levels (default: 6,7,8)",
    )
    args = ap.parse_args()

    levels = [int(x.strip()) for x in args.levels.split(",") if x.strip()]
    engine = create_engine(get_settings().database_url)
    rows: list[tuple[int, str, dict]] = []
    for level in levels:
        if args.cohort in ("all", "llm_fallback"):
            rows.extend((level, "llm_fallback", r) for r in fetch_llm_fallback(engine, level))
        if args.cohort in ("all", "bypass"):
            rows.extend((level, "bypass", r) for r in fetch_bypass_unverified(engine, level))

    if args.limit:
        rows = rows[: args.limit]

    stats = {"confirmed": 0, "disagreed": 0, "honest": 0, "empty": 0}
    log.info("P3 close queue: %d tasks levels=%s (dry_run=%s)", len(rows), levels, args.dry_run)
    for level, cohort, row in rows:
        outcome = process_row(engine, row, cohort, dry_run=args.dry_run)
        stats[outcome] = stats.get(outcome, 0) + 1
        if args.sleep and not args.dry_run:
            time.sleep(args.sleep)

    log.info("=" * 50)
    log.info("P3 close levels %s: %s", levels, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
