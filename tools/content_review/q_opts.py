import sys, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in sys.argv[1].split(","):
    c.execute("SELECT question_latex, correct_answer_latex, answer_options IS NOT NULL AND answer_options::text<>'[]', distractor_meta FROM tasks_master WHERE id=%s", (t,)); q, k, ao, dm = c.fetchone()
    print("##", t, "opts" if ao else "", "| K:", k[:200])
    for i, d in enumerate(dm or []): print("   ", i, (d.get("value") or "")[:200])
