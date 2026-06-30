#!/usr/bin/env python3
import sys, os
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
engine = create_engine(os.environ["DATABASE_URL"])
ids = [
    "G8_TB_17_394", "G8_TB_17_394.4", "G8_TB_17_395", "G8_TB_17_395.4",
    "G8_TB_47_1176", "G8_TB_47_1176.4", "G8_TB_47_1177", "G8_TB_47_1177.4",
    "G8_TB_48_1182", "G8_TB_48_1182.4",
]
with engine.connect() as c:
    for tid in ids:
        r = c.execute(text("""
            SELECT id, answer_type, correct_answer, question_text,
                   tags->>'split_parent_id' as sp,
                   tags->>'split_child_index' as si,
                   tags->>'compound_split' as cs,
                   tags->>'smart_verify_status' as sv
            FROM tasks_master WHERE id = :id
        """), {"id": tid}).fetchone()
        if not r:
            print(f"{tid}: NOT FOUND")
            continue
        print(f"=== {r.id} sv={r.sv} parent={r.sp} idx={r.si} compound={r.cs}")
        print(f"Q: {(r.question_text or '')[:160].replace(chr(10), ' ')}")
        print(f"A: {(r.correct_answer or '')[:90]}")
        print()
