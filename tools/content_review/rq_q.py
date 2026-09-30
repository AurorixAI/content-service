import sys, json, psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
a, b = int(sys.argv[1]), int(sys.argv[2])
T = json.load(open("/audit/rq_todo.json"))[a:b]
for i, t in enumerate(T, a):
    c.execute("SELECT regexp_replace(question_latex,'\\s+',' ','g'), regexp_replace(correct_answer_latex,'\\s+',' ','g') FROM tasks_master WHERE id=%s", (t,))
    q, k = c.fetchone()
    print(f"{i}|{t}\nQ: {q[:420]}\nK: {(k or '')[:700]}")
