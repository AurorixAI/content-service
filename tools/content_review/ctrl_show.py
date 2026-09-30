import sys, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
T = json.load(open("/audit/ctrl_todo.json"))[int(sys.argv[1]):int(sys.argv[2])]
for i, t in enumerate(T, int(sys.argv[1])):
    c.execute("SELECT regexp_replace(question_latex,'\\s+',' ','g'), correct_answer_latex, distractor_meta, is_active FROM tasks_master WHERE id=%s", (t,))
    q, k, d, a = c.fetchone()
    print(f"R{i}. {t}{'' if a else ' [INACTIVE]'} Q: {q[:280]}\n   K: {(k or '')[:140]} | D: {[str(x.get('value_latex') or x.get('value'))[:48] for x in d or []]}")
