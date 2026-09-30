import sys, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for pat in sys.argv[1].split(","):
    c.execute("SELECT id, is_active, question_latex, question_text, correct_answer_latex, distractor_meta FROM tasks_master WHERE id LIKE %s ORDER BY id", (pat,))
    for t, a, q, qt, k, d in c.fetchall():
        print("##", t, "" if a else "(INACTIVE)", "| K:", k, "| Q:", " ".join(q.split())[-110:])
        if qt != q: print("   RAW:", " ".join((qt or "").split())[-110:])
        print("   D:", [str(x.get("value"))[:40] for x in (d or [])])
