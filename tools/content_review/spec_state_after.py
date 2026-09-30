"""Post-write state of the tasks in a restore spec (for grader simulation)."""
import json, sys
import psycopg2
spec = json.load(open(sys.argv[1]))
cols = ["id", "answer_type", "question_text", "question_latex", "correct_answer", "correct_answer_latex", "answer_options", "answer_options_latex", "distractor_meta"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute(f"SELECT {', '.join(cols)} FROM tasks_master WHERE id = ANY(%s)", (sorted(spec),))
rows = []
for r in c.fetchall():
    t = dict(zip(cols, r)); t.update(spec[t["id"]]["fields"]); rows.append(t)
json.dump(rows, open("/audit/nested_after_state.json", "w"), ensure_ascii=False)
print(len(rows), "tasks")
