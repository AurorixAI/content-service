import sys, psycopg2, json
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in sys.argv[1].split(","):
    c.execute("SELECT question_latex, question_text, correct_answer_latex, distractor_meta FROM tasks_master WHERE id=%s", (t,)); q, qt, k, d = c.fetchone()
    print("##", t); print(" L:", json.dumps(q, ensure_ascii=False)); 
    if qt != q: print(" R:", json.dumps(qt, ensure_ascii=False))
    print(" K:", k, "| D:", [str(x.get("value"))[:60] for x in d or []])
