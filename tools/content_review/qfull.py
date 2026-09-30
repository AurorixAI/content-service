import sys, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for pat in sys.argv[1].split(","):
    c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta, source_reference, answer_type FROM tasks_master WHERE is_active AND id LIKE %s ORDER BY id", (pat,))
    for t, q, k, d, s, at in c.fetchall():
        print("##", t, at, "|", (s or "gen").split("::")[0][:8], (s or "").split("::")[-1]); print("  Q:", " ".join(q.split())); print("  K:", k); print("  D:", [x.get("value") for x in d or []])
