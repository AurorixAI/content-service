#!/usr/bin/env python3
"""Quick gate audit by class level."""
from __future__ import annotations

import json
import sys
from collections import Counter

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import stored_distractors_valid, validate_distractor_set

GRADE = int(sys.argv[1]) if len(sys.argv) > 1 else 8

e = create_engine(get_settings().database_url)
with e.connect() as c:
    rows = c.execute(
        text(
            """
      SELECT tm.id, tm.answer_type, tm.question_text, tm.correct_answer, tm.distractor_meta
      FROM tasks_master tm
      JOIN textbook_toc toc ON toc.id = tm.toc_id
      JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
      WHERE tb.class_level = :g
        AND jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) >= 2
    """
        ),
        {"g": GRADE},
    ).mappings().all()

ok = fail = 0
reasons: Counter = Counter()
fail_by_type: Counter = Counter()
for row in rows:
    d = row["distractor_meta"]
    if isinstance(d, str):
        d = json.loads(d)
    q = row["question_text"] or ""
    a = row["correct_answer"] or ""
    at = row["answer_type"] or ""
    if stored_distractors_valid(d, question=q, correct_answer=a, answer_type=at, min_count=2):
        ok += 1
        continue
    fail += 1
    fail_by_type[at or "?"] += 1
    _, rej = validate_distractor_set(
        d, question=q, correct_answer=a, answer_type=at, max_count=len(d)
    )
    for x in rej:
        reasons[x.get("gate_reason", "?")] += 1

print(f"G{GRADE} gate_ok={ok} gate_fail={fail} total={len(rows)}")
print("fail_by_type:", dict(fail_by_type.most_common(8)))
print("reasons:", dict(reasons.most_common(8)))
