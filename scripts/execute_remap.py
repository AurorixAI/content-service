#!/usr/bin/env python3
"""Execute toc_id remap for contaminated tasks."""
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text

e = create_engine("postgresql://algo:algo_password@content-postgres:5432/algo_content")
TID = "a7585f33-4f43-47b2-8ca6-c4ef6c8020c8"

# (source_para, ex_min, ex_max, target_para)
REMAPS = [
    ("\u0031\u20132",    54,  62,  "3\u20135"),
    ("\u0031\u20132",    63,  90,  "6\u20137"),
    ("13\u201314",      142, 156,  "15\u201316"),
    ("40\u201342",      363, 379,  "43\u201345"),
    ("40\u201342",      381, 409,  "46\u201348"),
    ("62\u201364",      567, 584,  "65\u201366"),
    ("98\u2013100",     873, 897,  "101\u2013102"),
]

total = 0
for src, mn, mx, dst in REMAPS:
    with e.connect() as c:
        row = c.execute(
            text("SELECT id FROM textbook_toc WHERE textbook_id=:t AND number=:n"),
            {"t": TID, "n": dst}
        ).fetchone()
        if not row:
            print(f"WARN: toc not found for {dst}")
            continue
        dst_id = row[0]  # keep original type (int or uuid)

        ids = [
            r[0] for r in c.execute(text("""
                SELECT tm.id
                FROM tasks_master tm
                JOIN textbook_toc t ON t.id = tm.toc_id
                JOIN textbook_tasks tt ON tt.task_id = tm.id
                WHERE t.textbook_id = :tid
                  AND t.number = :src
                  AND tt.exercise_number ~ '^[0-9]+$'
                  AND tt.exercise_number::int BETWEEN :mn AND :mx
            """), {"tid": TID, "src": src, "mn": mn, "mx": mx}).fetchall()
        ]

    if not ids:
        print(f"  skip {src} ex{mn}-{mx}: 0")
        continue

    with e.begin() as c:
        c.execute(
            text("UPDATE tasks_master SET toc_id = :new WHERE id = ANY(:ids)"),
            {"new": dst_id, "ids": ids}
        )
        c.execute(
            text("UPDATE textbook_tasks SET paragraph_number = :p WHERE task_id = ANY(:ids) AND textbook_id = :tid"),
            {"p": dst, "ids": ids, "tid": TID}
        )

    print(f"  OK  {src} ex{mn}-{mx} -> {dst}: {len(ids)} tasks")
    total += len(ids)

print(f"\nTotal remapped: {total} tasks")
