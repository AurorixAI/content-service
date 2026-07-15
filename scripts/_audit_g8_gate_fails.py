#!/usr/bin/env python3
"""Fast G8 gate-fail list with source tags (no full re-validation)."""
from __future__ import annotations

import json
import sys
from collections import Counter

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings
from src.pipeline.distractor_gate import stored_distractors_valid, validate_distractor_set

GRADE = 8
e = create_engine(get_settings().database_url)
with e.connect() as c:
    rows = c.execute(
        text(
            """
      SELECT tm.id, tm.answer_type, tm.correct_answer, tm.distractor_meta, tm.tags
      FROM tasks_master tm
      JOIN textbook_toc toc ON toc.id = tm.toc_id
      JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
      WHERE tb.class_level = :g
        AND jsonb_array_length(COALESCE(distractor_meta, '[]'::jsonb)) >= 2
    """
        ),
        {"g": GRADE},
    ).mappings().all()

sources: Counter = Counter()
reasons: Counter = Counter()
fails: list[str] = []

for row in rows:
    d = row["distractor_meta"]
    if isinstance(d, str):
        d = json.loads(d)
    q = row.get("question_text") or ""
    a = row["correct_answer"] or ""
    at = row["answer_type"] or ""
    if stored_distractors_valid(d, question=q, correct_answer=a, answer_type=at, min_count=2):
        continue
    _, rej = validate_distractor_set(
        d, question=q, correct_answer=a, answer_type=at, max_count=len(d)
    )
    for x in rej:
        reasons[x.get("gate_reason", "?")] += 1
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
    sources[src] += 1
    fails.append(row["id"])
    print(f"{row['id']}\t{at}\t{src}\t{[x.get('gate_reason') for x in rej]}\t{a[:50]}")

print("---")
print(f"total_fail={len(fails)}")
print("sources:", dict(sources.most_common()))
print("reasons:", dict(reasons.most_common()))
