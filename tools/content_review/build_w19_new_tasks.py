"""Build data/content_repairs/n01-2026-10-08-w19-new-tasks.json: top up thin G10/G11 L4 skills to >=5 active tasks.
Sources: audit/f1p/new_tasks/<skill>.json (each from gen_<skill>.py, sympy-verified). The shortfall was recomputed
against the local DB with w19-polish already applied; where a skill needed fewer tasks than were written
(KEEP below) only the listed difficulty is kept.   python3 -m tools.content_review.build_w19_new_tasks
"""
import json
from pathlib import Path

from tools.content_review.build_w15_new_tasks import ROOT, row

SRC = Path(__file__).resolve().parent / "audit" / "f1p" / "new_tasks"
OUT = ROOT / "data" / "content_repairs" / "n01-2026-10-08-w19-new-tasks.json"
BATCH = "f1-authoring-2026-10-08-thin"
KEEP = {"G11_S26_01": ["B"]}      # skill already has 4 active after w19: one more task is enough


def build():
    rows = []
    for f in sorted(SRC.glob("G1*.json")):
        s = f.stem
        tasks = json.loads(f.read_text())
        if s in KEEP:
            tasks = [t for t in tasks if t["diff"] in KEEP[s]][:len(KEEP[s])]
        rows += [row(t, BATCH) for t in tasks]
    return {"batch": BATCH, "mode": "insert_new_tasks", "source_checked_at": "2026-10-08T00:00:00Z",
            "student_data_included": False, "new_tasks": rows}


if __name__ == "__main__":
    m = build()
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    from collections import Counter
    c = Counter(r["skill_id"] for r in m["new_tasks"])
    print(OUT, len(m["new_tasks"]), "tasks,", len(c), "skills")
