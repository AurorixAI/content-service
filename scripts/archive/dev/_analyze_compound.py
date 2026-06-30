#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings

TB = "b8f4a2c1-3d5e-4f60-9182-3456789abcde"
engine = create_engine(get_settings().database_url)

CAND_SQL = """
    SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type,
           tm.tags->>'smart_verify_status' AS sv
    FROM tasks_master tm
    JOIN textbook_tasks tt ON tt.task_id = tm.id AND tt.textbook_id = CAST(:tid AS UUID)
    WHERE (
        (tm.question_text LIKE '%%1)%%' AND tm.question_text LIKE '%%2)%%')
        OR (tm.question_text ~* '(^|[;\\n|])[[:space:]]*[а-г]\\)'
            AND tm.question_text ~* '(^|[;\\n|])[[:space:]]*[б-г]\\)')
        OR (tm.question_text ~* 'д\\)' AND tm.correct_answer LIKE '%%;%%')
    )
"""

with engine.connect() as c:
    rows = c.execute(text(CAND_SQL + " ORDER BY tm.id"), {"tid": TB}).mappings().all()
    total_tb = c.execute(text("""
        SELECT COUNT(*) FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        WHERE toc.textbook_id = CAST(:tid AS UUID)
    """), {"tid": TB}).scalar()
    split_children = c.execute(text("""
        SELECT COUNT(*) FROM tasks_master tm
        JOIN textbook_toc toc ON toc.id = tm.toc_id
        WHERE toc.textbook_id = CAST(:tid AS UUID) AND tm.tags ? 'split_from'
    """), {"tid": TB}).scalar()

# Check existing children by prefix
no_children = []
has_children = []
for row in rows:
    tid = row["id"]
    with engine.connect() as c:
        n = c.execute(
            text("SELECT COUNT(*) FROM tasks_master WHERE id LIKE :pfx"),
            {"pfx": tid + ".%"},
        ).scalar()
    if n:
        has_children.append((tid, n, row["sv"]))
    else:
        no_children.append(row)

print(f"G8 TB total: {total_tb}")
print(f"Split children already in DB: {split_children}")
print(f"Compound SQL candidates: {len(rows)}")
print(f"  WITHOUT .N children yet: {len(no_children)}")
print(f"  WITH .N children already: {len(has_children)}")
print()

from collections import Counter
sv = Counter(r["sv"] or "pending" for r in rows)
print("Verify status of candidates:")
for k, v in sv.most_common():
    print(f"  {k}: {v}")

import re
dezh = sum(1 for r in rows if re.search(r"[дежз]\)", r["question_text"] or "", re.I))
num = sum(1 for r in rows if "1)" in (r["question_text"] or "") and "2)" in (r["question_text"] or ""))
print()
print(f"Pattern: д)е)ж)з) style: {dezh}")
print(f"Pattern: 1) 2) numeric: {num}")
print()
print("No children yet (first 15) — these are the REAL unsplit compounds:")
for r in no_children[:15]:
    print(f"  {r['id']} sv={r['sv']}")
    print(f"    A: {(r['correct_answer'] or '')[:65]}")
