import sys, json, psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
a, b = int(sys.argv[1]), int(sys.argv[2]); lo = int(sys.argv[3]) if len(sys.argv) > 3 else 100; hi = int(sys.argv[4]) if len(sys.argv) > 4 else 600
T = json.load(open("/audit/rq_todo.json"))[a:b]
for i, t in enumerate(T, a):
    c.execute("SELECT regexp_replace(correct_answer_latex,'\\s+',' ','g') FROM tasks_master WHERE id=%s", (t,))
    k = c.fetchone()[0] or ''
    if len(k) > lo: print(f"{i}|...{k[lo:hi]}")
