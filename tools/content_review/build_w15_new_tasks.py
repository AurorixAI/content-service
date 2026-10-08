"""Build data/content_repairs/n01-2026-10-07-w15-new-tasks.json (insert manifest, key "new_tasks").

Sources: tools/content_review/audit/f1/new_tasks/<skill>.json, produced by the per-skill
gen_<skill>.py scripts there (every key and every distractor value is computed with
sympy from the described mistake; run audit/f1/new_tasks/run_all.sh to re-verify).
Run from content-service:  python3 -m tools.content_review.build_w15_new_tasks
"""
import json
from pathlib import Path

from tools.content_review.guarded_insert import IRT_DIFFICULTY, validate_new_task
from tools.content_review.guarded_repair import FIELDS, fingerprint

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "audit" / "f1" / "new_tasks"
OUT = ROOT / "data" / "content_repairs" / "n01-2026-10-07-w15-new-tasks.json"
BATCH = "f1-authoring-2026-10-07"
SKILLS = ["G11_S01_01", "G11_S01_03", "G11_S02_01", "G11_S05_01", "G11_S05_02", "G11_S07_03", "G11_S08_01",
          "G11_S08_02", "G11_S14_02", "G11_S16_02", "G11_S31_02", "G11_S39_03", "G11_S40_02", "G11_S44_01"]
TAGS = {"content_review": {"batch": BATCH, "author": "claude-sonnet", "verified_by": "sympy"}}


def row(t, batch=BATCH):
    options = [t["key"]] + [d for d, _ in t["ds"]]
    meta = [{"value": d, "value_latex": d, "error_type": "manual_generated", "plausibility": 0.7,
             "error_logic": e, "error_logic_latex": e, "explanation": e, "explanation_latex": e}
            for d, e in t["ds"]]
    r = {"id": t["id"], "skill_id": t["skill"], "question_text": t["q"], "question_latex": t["q"],
         "question_image_url": None, "answer_type": "multiple_choice",
         "correct_answer": t["key"], "correct_answer_latex": t["key"], "sympy_solution": None,
         "answer_options": options, "answer_options_latex": list(options),
         "difficulty": t["diff"], "irt_discrimination": 1.0, "irt_difficulty": IRT_DIFFICULTY[t["diff"]],
         "irt_guessing": 0.2, "distractor_meta": meta, "is_active": True, "toc_id": None,
         "cognitive_load": "apply", "verification_status": "verified", "source_type": "ai_generated",
         "source_reference": None, "tags": {"content_review": {**TAGS["content_review"], "batch": batch}}, "is_star": False,
         "task_category": "standard", "latex_status": None}
    assert set(r) == set(FIELDS) | {"id"}
    validate_new_task(r, batch)
    r["after_sha256"] = fingerprint(r)
    return r


def build():
    rows = []
    for s in SKILLS:
        tasks = json.loads((SRC / f"{s}.json").read_text())
        assert len(tasks) == 7 and [t["diff"] for t in tasks].count("A") == 2, s
        rows += [row(t) for t in tasks]
    return {"batch": BATCH, "mode": "insert_new_tasks", "source_checked_at": "2026-10-07T00:00:00Z",
            "student_data_included": False, "new_tasks": rows}


if __name__ == "__main__":
    m = build()
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
    print(OUT, len(m["new_tasks"]), "tasks")
