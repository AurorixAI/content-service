import sys, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in sys.argv[1].split(","):
    c.execute("SELECT question_latex, correct_answer_latex, distractor_meta, source_reference FROM tasks_master WHERE id=%s", (t,)); r = c.fetchone()
    if not r: print("##", t, "MISSING"); continue
    q, k, d, s = r
    print("##", t, "|", (s or "")[:50]); print(" Q:", " ".join(q.split())[:int(sys.argv[2]) if len(sys.argv) > 2 else 300]); print(" K:", " ".join((k or "").split())[:200]); print(" D:", [x.get("value", "")[:50] for x in (d or [])])
