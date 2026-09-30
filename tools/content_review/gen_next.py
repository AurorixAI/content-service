import sys, psycopg2
pref, after, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, regexp_replace(question_latex,'\\s+',' ','g'), correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND id LIKE %s AND id > %s ORDER BY id LIMIT %s", (pref + "%", after, n))
for t, q, k, d in c.fetchall():
    print(f"{t} Q: {q[:430]}\n   K: {(k or '')[:120]} | D: {[str(x.get('value_latex') or x.get('value'))[:44] for x in d or []]}")
