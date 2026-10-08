"""Build data/content_repairs/n01-2026-10-08-w17-new-tasks.json (insert manifest) for the two skills that
would otherwise be left without genuine tasks: G11_S01_02 and G11_S13_01.
Sources: audit/f1/new_tasks/<skill>.json from gen_<skill>.py (sympy-verified). Run from content-service:
  python3 -m tools.content_review.build_w17_new_tasks
"""
import json

from tools.content_review.build_w15_new_tasks import ROOT, SRC, row

OUT = ROOT / "data" / "content_repairs" / "n01-2026-10-08-w17-new-tasks.json"
BATCH = "f1-authoring-2026-10-08"
SKILLS = ["G11_S01_02", "G11_S13_01"]


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
