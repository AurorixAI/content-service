#!/usr/bin/env python3
"""Analyze G6 gate fails: how many fix via trim / deterministic / need-LLM."""
from __future__ import annotations

import json
import sys
from collections import Counter

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import (
    gate_clean_distractor_meta,
    stored_distractors_valid,
    validate_distractor_set,
)
from src.pipeline.distractors import (
    _chain_inequality_candidates,
    _numeric_offset_candidates,
    _prose_template_candidates,
    _relation_flip_candidates,
)

LEVEL = 6
_TEXT = frozenset({"text", "open_text", "coordinate"})


def _dmeta(raw):
    if isinstance(raw, list):
        return raw
    return json.loads(raw or "[]")


def _det_candidates(ans: str, at: str, q: str) -> list[str]:
    c: list[str] = []
    if at in _TEXT or at in ("inequality", "multiple_choice", "set"):
        c.extend(_chain_inequality_candidates(ans))
        c.extend(_relation_flip_candidates(ans))
        c.extend(_prose_template_candidates(ans, q))
    if at in ("exact_number", "decimal", "fraction", "expression"):
        c.extend(_numeric_offset_candidates(ans))
    seen, out = set(), []
    for v in c:
        k = v.strip().casefold()
        if k and k not in seen:
            seen.add(k)
            out.append(v.strip())
    return out


def main() -> int:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        rows = c.execute(
            text(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
                       tm.distractor_meta
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :lvl
                  AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) >= 2
                ORDER BY tm.id
                """
            ),
            {"lvl": LEVEL},
        ).mappings().all()

    buckets: Counter = Counter()
    by_type_need_llm: Counter = Counter()
    trim_ok, det_ok, need_llm = [], [], []

    for r in rows:
        q = r["question_text"] or ""
        ans = r["correct_answer"] or ""
        at = (r["answer_type"] or "").lower()
        dm = _dmeta(r["distractor_meta"])
        if stored_distractors_valid(dm, question=q, correct_answer=ans, answer_type=at, min_count=2):
            continue  # already good
        # this is a gate fail
        buckets["gate_fail"] += 1

        # try trim
        cleaned = gate_clean_distractor_meta(
            dm, question=q, correct_answer=ans, answer_type=at, min_count=2, max_count=3
        )
        if cleaned and len(cleaned) >= 2:
            buckets["trim_ok"] += 1
            trim_ok.append(r["id"])
            continue

        # try trim + deterministic top-up
        kept = cleaned or []
        skip_l3 = at in _TEXT or at in ("inequality", "set")
        cand = _det_candidates(ans, at, q)
        items = [{"value": v, "error_logic": "x" * 12, "explanation": "x" * 12} for v in cand]
        acc, _ = validate_distractor_set(
            items, question=q, correct_answer=ans, answer_type=at, max_count=3, skip_l3=skip_l3
        )
        # merge kept + acc unique
        vals = {str(d.get("value", "")).strip().casefold() for d in kept}
        merged = list(kept)
        for d in acc:
            v = str(d.get("value", "")).strip().casefold()
            if v not in vals:
                merged.append(d)
                vals.add(v)
        if len(merged) >= 2:
            buckets["det_ok"] += 1
            det_ok.append(r["id"])
            continue

        buckets["need_llm"] += 1
        by_type_need_llm[at] += 1
        need_llm.append(r["id"])

    print("=" * 60)
    print("G6 GATE FIX FEASIBILITY")
    print("=" * 60)
    for k in ("gate_fail", "trim_ok", "det_ok", "need_llm"):
        print(f"  {k:12} {buckets[k]}")
    print("\nneed_llm by type:", dict(by_type_need_llm.most_common()))

    import pathlib
    pathlib.Path("/app/scripts/g6_gate_plan.json").write_text(
        json.dumps(
            {"trim_ok": trim_ok, "det_ok": det_ok, "need_llm": need_llm},
            ensure_ascii=False,
            indent=1,
        )
    )
    print(f"\nWrote g6_gate_plan.json (trim={len(trim_ok)} det={len(det_ok)} llm={len(need_llm)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
