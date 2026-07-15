#!/usr/bin/env python3
"""Dump remaining G6 gate fails with full diagnostic detail."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict

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


def _det_candidates(ans, at, q):
    c = []
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
                SELECT tm.id, tm.answer_type, tm.question_text, tm.correct_answer,
                       tm.distractor_meta, tm.tags
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id=tm.toc_id
                JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
                WHERE tb.class_level = :lvl
                  AND jsonb_array_length(COALESCE(tm.distractor_meta,'[]')) >= 2
                ORDER BY tm.id
                """
            ),
            {"lvl": LEVEL},
        ).mappings().all()

    fails = []
    for r in rows:
        q, ans, at = r["question_text"] or "", r["correct_answer"] or "", (r["answer_type"] or "").lower()
        dm = _dmeta(r["distractor_meta"])
        if stored_distractors_valid(dm, question=q, correct_answer=ans, answer_type=at, min_count=2):
            continue
        _, rej = validate_distractor_set(dm, question=q, correct_answer=ans, answer_type=at, max_count=len(dm))
        reasons = [x.get("gate_reason") for x in rej]
        dist_vals = [str(d.get("value", ""))[:60] for d in dm if isinstance(d, dict)]
        trimmed = gate_clean_distractor_meta(dm, question=q, correct_answer=ans, answer_type=at, min_count=2, max_count=3)
        det = _det_candidates(ans, at, q)
        tags = r["tags"] if isinstance(r["tags"], dict) else json.loads(r["tags"] or "{}")
        fails.append(
            {
                "id": r["id"],
                "answer_type": at,
                "correct_answer": ans[:80],
                "gate_reasons": reasons,
                "distractors": dist_vals,
                "trim_kept": len(trimmed) if trimmed else 0,
                "det_cands": len(det),
                "fix_g6_gate": tags.get("fix_g6_gate"),
                "had_llm": tags.get("fix_g6_gate") == "llm",
            }
        )

    print(f"Remaining gate fails: {len(fails)}")
    by_type = Counter(f["answer_type"] for f in fails)
    by_reason = Counter(r for f in fails for r in f["gate_reasons"])
    by_trim = Counter(f["trim_kept"] for f in fails)
    by_fix = Counter(f.get("fix_g6_gate") or "never" for f in fails)
    fixable_trim = sum(1 for f in fails if f["trim_kept"] >= 2)
    fixable_det = sum(1 for f in fails if f["trim_kept"] < 2 and f["det_cands"] > 0)
    need_llm = sum(1 for f in fails if f["trim_kept"] < 2 and f["det_cands"] == 0)

    print("\nBy type:", dict(by_type.most_common()))
    print("By reason:", dict(by_reason.most_common()))
    print("By prior fix:", dict(by_fix.most_common()))
    print("Trim kept count:", dict(by_trim.most_common()))
    print(f"\nFixability: trim_ok={fixable_trim} need_det={fixable_det} need_llm_only={need_llm}")

    # Group by primary reason + type for strategy
    groups = defaultdict(list)
    for f in fails:
        key = (f["answer_type"], f["gate_reasons"][0] if f["gate_reasons"] else "?")
        groups[key].append(f["id"])

    print("\n=== GROUPS (type, primary_reason) -> count ===")
    for (at, reason), ids in sorted(groups.items(), key=lambda x: -len(x[1])):
        print(f"  {at:16s} {reason:20s} {len(ids):3d}")
        for tid in ids[:3]:
            f = next(x for x in fails if x["id"] == tid)
            print(f"    {tid}  ans={f['correct_answer']!r}")
            print(f"      dist={f['distractors']}")
            print(f"      reasons={f['gate_reasons']} trim={f['trim_kept']} det={f['det_cands']}")

    import pathlib
    pathlib.Path("/app/scripts/g6_gate_remaining.json").write_text(
        json.dumps(fails, ensure_ascii=False, indent=1)
    )
    print(f"\nWrote g6_gate_remaining.json ({len(fails)} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
