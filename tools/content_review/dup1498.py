import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
N = lambda q: re.sub(r"\\square|\[\?\]|▢|\s|\$|\{,\}|,", "", q.split(".", 1)[-1])
c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND id ~ '^G5_TB_63_149[89]'")
g = {}
for t, q, k, d in c.fetchall(): g.setdefault((N(q), re.sub(r"[\s$]", "", k)), []).append((t, len(d or [])))
for key, v in sorted(g.items()): print(key, v)
