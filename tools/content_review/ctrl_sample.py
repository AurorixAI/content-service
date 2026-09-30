import sys, random, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, regexp_replace(question_latex,'\\s+',' ','g'), correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active ORDER BY id")
R = c.fetchall(); random.Random(260926).shuffle(R); R = R[:300]
json.dump([r[0] for r in R], open("/audit/ctrl300_ids.json", "w"))
a, b = int(sys.argv[1]), int(sys.argv[2])
for i, (t, q, k, d) in enumerate(R[a:b], a):
    print(f"{i}. {t} Q: {q[:300]}\n   K: {(k or '')[:150]} | D: {[str(x.get('value_latex') or x.get('value'))[:50] for x in d or []]}")
