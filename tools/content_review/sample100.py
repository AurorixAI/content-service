# -*- coding: utf-8 -*-
"""Random sample of 100 active tasks (seed fixed) for a careful manual review; state for diag/exam simulation."""
import json, random, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id FROM tasks_master WHERE is_active ORDER BY id")
ids = [r[0] for r in c.fetchall()]
random.seed(20260925)
pick = sorted(random.sample(ids, 100))
cols = ["id", "source_reference", "answer_type", "question_text", "question_latex", "correct_answer", "correct_answer_latex",
        "answer_options", "answer_options_latex", "distractor_meta"]
c.execute(f"SELECT {', '.join(cols)} FROM tasks_master WHERE id = ANY(%s) ORDER BY id", (pick,))
rows = [dict(zip(cols, r)) for r in c.fetchall()]
json.dump(rows, open("/audit/nested_after_state.json", "w"), ensure_ascii=False)
json.dump({r["id"]: {"fields": {}} for r in rows}, open("/audit/sample100_spec.json", "w"))
with open("/audit/sample100.txt", "w") as f:
    for n, t in enumerate(rows, 1):
        src = (t["source_reference"] or "").split("::", 1)[-1]
        f.write(f"### {n}. {t['id']} [{t['answer_type']}] src={src}\n")
        f.write("Q: " + " ".join((t["question_latex"] or "").split()) + "\n")
        f.write("K: " + (t["correct_answer_latex"] or "") + "   | raw: " + (t["correct_answer"] or "") + "\n")
        for d in t["distractor_meta"] or []:
            if isinstance(d, dict):
                f.write("  D: " + str(d.get("value_latex") or d.get("value")) + "   || " + " ".join(str(d.get("error_logic") or "").split())[:160] + "\n")
        if t["answer_options_latex"]:
            f.write("  STORED OPTS: " + " ¦ ".join(str(o.get("text") if isinstance(o, dict) else o) for o in t["answer_options_latex"]) + "\n")
print(len(rows))
