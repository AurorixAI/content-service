"""Build data/content_repairs/n01-2026-10-08-w18-new-tasks.json (insert manifest) for nine grade-10 skills that
have no genuine tasks after remapping: G10_S03_06 S04_07 S07_08 S13_02 S22_05 S22_07.
Sources: audit/f1/new_tasks/<skill>.json from gen_<skill>.py (sympy-verified). Run from content-service:
  python3 -m tools.content_review.build_w18_new_tasks
"""
import json

from tools.content_review.build_w15_new_tasks import ROOT, SRC, row

OUT = ROOT / "data" / "content_repairs" / "n01-2026-10-08-w18-new-tasks.json"
BATCH = "f1-authoring-2026-10-08-g10"
SKILLS = ["G10_S03_06", "G10_S04_07", "G10_S07_08", "G10_S13_02", "G10_S22_05", "G10_S22_07",
          "G10_S05_06", "G10_S06_09", "G10_S23_07"]


def build():
    rows = []
    for s in SKILLS:
        tasks = json.loads((SRC / f"{s}.json").read_text())
        assert len(tasks) == 7 and [t["diff"] for t in tasks].count("A") == 2, s
        rows += [row(t, BATCH) for t in tasks]
    return {"batch": BATCH, "mode": "insert_new_tasks", "source_checked_at": "2026-10-08T00:00:00Z",
            "student_data_included": False, "new_tasks": rows}


if __name__ == "__main__":
    m = build()
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    print(OUT, len(m["new_tasks"]), "tasks")
