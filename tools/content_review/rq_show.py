import sys, json, psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
T = json.load(open("/audit/rq_todo.json"))[int(sys.argv[1]):int(sys.argv[2])]
for i, t in enumerate(T, int(sys.argv[1])):
    c.execute("SELECT regexp_replace(question_latex,'\\s+',' ','g'), correct_answer_latex FROM tasks_master WHERE id=%s", (t,))
    q, k = c.fetchone()
    print(f"{i}|{t}|Q: {q[:230]}|K: {(k or '')[:110]}")
