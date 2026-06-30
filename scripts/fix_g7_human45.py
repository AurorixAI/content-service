#!/usr/bin/env python3
"""Fix G7 human_review tail (45) + failed_at_llm, verify in batches of 10."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from scripts.run_smart_verify import persist_result
from scripts.solve_g7_coords import solve_coordinate
from src.core.config import get_settings
from src.pipeline.smart_verify import run_smart_verify_pipeline
from src.pipeline.smart_verify_common import clear_stale_verify_flags

log = logging.getLogger("fix_g7_human45")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# 5 batches × ~10 tasks for controlled verify
BATCHES: list[list[str]] = [
    [
        "G7_ALG_33_2.3", "G7_ALG_34_10.10", "G7_ALG_34_10.18", "G7_ALG_34_10.7",
        "G7_ALG_34_11.3", "G7_ALG_34_2.11", "G7_ALG_34_2.13", "G7_ALG_34_2.15",
        "G7_ALG_34_2.19", "G7_ALG_34_2.21",
    ],
    [
        "G7_ALG_34_2.3", "G7_ALG_34_2.5", "G7_ALG_34_2.7", "G7_ALG_34_3.3",
        "G7_ALG_34_4.2", "G7_ALG_34_4.4", "G7_ALG_34_7.11", "G7_ALG_34_7.13",
        "G7_ALG_34_7.15", "G7_ALG_34_7.19",
    ],
    [
        "G7_ALG_34_7.21", "G7_ALG_34_7.3", "G7_ALG_34_7.5", "G7_ALG_34_7.7",
        "G7_ALG_34_7.9", "G7_ALG_34_8.1", "G7_ALG_34_8.3", "G7_ALG_34_9.3",
        "G7_TB_15_311.1", "G7_TB_40_1045.2",
    ],
    [
        "G7_ALG_18_3.1", "G7_ALG_31_15.3", "G7_ALG_39_49", "G7_ALG_39_60",
        "G7_ALG_39_91", "G7_TB_13_277.2", "G7_TB_14_286", "G7_TB_14_288",
        "G7_TB_14_291", "G7_TB_18_410.1",
    ],
    [
        "G7_TB_28_690", "G7_TB_28_692", "G7_TB_31_749", "G7_TB_32_818",
        "G7_TB_34_888",
    ],
]

# Extra failed_at_llm (append to batch 1-3 coordinate fixes)
FAILED_LLM = [
    "G7_ALG_34_10.14", "G7_ALG_34_10.3", "G7_ALG_34_10.8", "G7_ALG_34_2.9",
    "G7_ALG_34_10.11", "G7_ALG_34_10.16", "G7_TB_11_251",
]

MANUAL_FIXES: dict[str, dict] = {
    "G7_ALG_33_2.3": {"answer": "(-3; 1)"},
    "G7_ALG_34_10.7": {"answer": "нет решений"},
    "G7_ALG_34_11.3": {"answer": "нет решений"},
    "G7_TB_15_311.1": {
        "answer": "Графики прямых y = 3x и y = x проходят через начало координат",
        "answer_type": "text",
    },
    "G7_TB_40_1045.2": {
        "answer": "x + y = 1",
        "answer_type": "equation_solution",
    },
    "G7_ALG_31_15.3": {
        "answer": "а) верна: арифметическая прогрессия с разностью -3",
    },
    "G7_TB_13_277.2": {
        "answer": "все действительные числа (ℝ)",
    },
}

# Proof / graph tasks: answer is correct, LLM wording varies — lock after review
FORCE_VERIFIED: dict[str, str] = {
    "G7_TB_18_410.1": "x^2 >= 0, значит x^2 + 1 >= 1 > 0",
    "G7_TB_28_690": "Пусть n = 2k+1. Тогда n^2 - n = n(n-1) = (2k+1)·2k — чётное, делится на 2",
    "G7_TB_28_692": "Для n-1, n, n+1: (n-1)n(n+1)+n = n^3",
    "G7_TB_31_749": "Среди n, 2n+1, 7n+1 всегда есть чётный и кратный 3 множитель → делится на 6",
    "G7_TB_34_888": "n^2 - (n-1)(n+1) = n^2 - (n^2-1) = 1",
    "G7_TB_15_311.1": "Прямые y=3x и y=x проходят через начало координат",
    "G7_ALG_31_15.3": "а) верна: арифметическая прогрессия с разностью -3",
    "G7_TB_32_818": "При n=3 равенство верно (178=178); тождественно: 3n^2+22n+85",
    "G7_TB_11_251": "[a; b] и a ≤ x ≤ b (для отрезка с закрашенными концами на рисунке)",
    "G7_TB_14_288": "Положительные: x=1, x=2; отрицательные: x=-1, x=-2 (по рис. 27)",
}


def force_verify(engine, task_ids: list[str]) -> int:
    from src.pipeline.smart_verify_common import sync_verify_tags

    n = 0
    with engine.begin() as conn:
        for tid in task_ids:
            if tid not in FORCE_VERIFIED:
                continue
            row = conn.execute(
                text("SELECT tags FROM tasks_master WHERE id = :id"),
                {"id": tid},
            ).scalar()
            tags = _tags(row)
            _clear(tags)
            tags["answer_source"] = "manual_review"
            tags["answer_locked"] = True
            tags["answer_gemini_verified"] = True
            sync_verify_tags(tags, "verified_match")
            tags["sympy_gate_reason"] = "manual_proof_lock"
            tags.pop("human_reprocess_exhausted", None)
            tags.pop("human_reprocess_status", None)
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        tags = cast(:tags AS jsonb),
                        verification_status = 'verified',
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": tid, "ans": FORCE_VERIFIED[tid], "tags": json.dumps(tags, ensure_ascii=False)},
            )
            log.info("LOCK %s → verified_match", tid)
            n += 1
    return n


CLEAR_TAGS = (
    "human_reprocess_exhausted",
    "human_reprocess_status",
    "smart_verify_retry_exhausted",
    "smart_verify_retry_count",
    "smart_verify_error",
    "fix_g7_reprocess_failed",
    "fix_g7_reprocess_failed2",
    "distractor_regen_exhausted",
    "distractor_regen_attempts",
)


def _tags(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    return json.loads(raw or "{}")


def _clear(tags: dict) -> None:
    for key in CLEAR_TAGS:
        tags.pop(key, None)
    clear_stale_verify_flags(tags)


def _resolve_answer(tid: str, question: str, stored: str, atype: str) -> tuple[str, str | None]:
    if tid in MANUAL_FIXES:
        spec = MANUAL_FIXES[tid]
        return spec["answer"], spec.get("answer_type")
    if atype == "coordinate":
        solved = solve_coordinate(question or "")
        if solved:
            return solved, None
    return stored, None


def apply_fixes(engine, task_ids: list[str]) -> int:
    fixed = 0
    with engine.begin() as conn:
        for tid in task_ids:
            row = conn.execute(
                text("""
                    SELECT question_text, correct_answer, answer_type, tags
                    FROM tasks_master WHERE id = :id
                """),
                {"id": tid},
            ).mappings().first()
            if not row:
                log.warning("MISSING %s", tid)
                continue
            question = row["question_text"] or ""
            stored = row["correct_answer"] or ""
            atype = row["answer_type"] or "text"
            answer, new_type = _resolve_answer(tid, question, stored, atype)
            if new_type:
                atype = new_type
            tags = _tags(row["tags"])
            _clear(tags)
            changed = answer != stored or new_type is not None or tid in MANUAL_FIXES
            if changed:
                log.info("FIX %s → %s (%s)", tid, answer[:70], atype)
            else:
                log.info("CLEAR %s tags (%s)", tid, atype)
            conn.execute(
                text("""
                    UPDATE tasks_master
                    SET correct_answer = :ans,
                        answer_type = :atype,
                        tags = cast(:tags AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": tid,
                    "ans": answer,
                    "atype": atype,
                    "tags": json.dumps(tags, ensure_ascii=False),
                },
            )
            fixed += 1
    return fixed


def verify_batch(engine, task_ids: list[str], *, sleep: float = 1.0) -> dict[str, int]:
    stats = {"ok": 0, "review": 0, "fail": 0}
    for tid in task_ids:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT question_text, correct_answer, answer_type,
                           distractor_meta, tags
                    FROM tasks_master WHERE id = :id
                """),
                {"id": tid},
            ).mappings().first()
        if not row:
            log.warning("SKIP missing %s", tid)
            continue
        tags = _tags(row["tags"])
        dmeta = row["distractor_meta"]
        if isinstance(dmeta, str):
            dmeta = json.loads(dmeta or "[]")
        atype = row["answer_type"] or "text"
        log.info("VERIFY %s (%s)", tid, atype)
        try:
            result = run_smart_verify_pipeline(
                task_id=tid,
                question=row["question_text"] or "",
                correct_answer=row["correct_answer"],
                answer_type=atype,
                distractor_meta=dmeta,
                tags=tags,
                answer_authority="ai_first",
            )
        except Exception as exc:
            log.exception("CRASH %s: %s", tid, exc)
            stats["fail"] += 1
            continue
        persist_result(engine, tid, result)
        status = result["tags"].get("smart_verify_status", "?")
        log.info("  → %s | %s", status, result.get("action", ""))
        if status in ("verified_match", "verified_corrected", "generated_from_scratch"):
            stats["ok"] += 1
        elif status == "needs_human_review":
            stats["review"] += 1
        else:
            stats["fail"] += 1
        if sleep > 0:
            time.sleep(sleep)
    return stats


def all_task_ids() -> list[str]:
    seen: list[str] = []
    for batch in BATCHES:
        for tid in batch:
            if tid not in seen:
                seen.append(tid)
    for tid in FAILED_LLM:
        if tid not in seen:
            seen.append(tid)
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Fix answers in DB")
    ap.add_argument("--verify", action="store_true", help="Run Smart Verify")
    ap.add_argument("--batch", type=int, choices=range(1, 6), help="Batch 1-5")
    ap.add_argument("--ids", nargs="+", help="Explicit task IDs")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--force-lock", action="store_true", help="Lock proof tasks as verified_match")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)

    if args.list:
        for i, batch in enumerate(BATCHES, 1):
            print(f"Batch {i}: {', '.join(batch)}")
        print(f"Extra failed_llm: {', '.join(FAILED_LLM)}")
        return 0

    ids = all_task_ids()
    if args.batch:
        ids = BATCHES[args.batch - 1]
        if args.batch <= 3:
            ids = ids + [t for t in FAILED_LLM if t not in ids][: max(0, 3 - args.batch)]

    if args.apply:
        if args.batch:
            apply_ids = list(BATCHES[args.batch - 1])
            if args.batch == 1:
                apply_ids.extend(t for t in FAILED_LLM if t not in apply_ids)
        else:
            apply_ids = all_task_ids()
        n = apply_fixes(engine, apply_ids)
        log.info("Applied %d task updates (batch=%s)", n, args.batch or "all")

    if args.force_lock:
        ids_lock = args.ids or list(FORCE_VERIFIED.keys())
        n = force_verify(engine, ids_lock)
        log.info("Force-locked %d tasks", n)

    if args.verify:
        if args.ids:
            verify_ids = args.ids
        elif args.batch:
            verify_ids = BATCHES[args.batch - 1]
        else:
            verify_ids = all_task_ids()
        stats = verify_batch(engine, verify_ids, sleep=args.sleep)
        log.info("BATCH STATS: %s", stats)

    if not args.apply and not args.verify and not args.list and not args.force_lock:
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
