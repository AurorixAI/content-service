import sys, random, psycopg2
tb, seed, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, split_part(source_reference,'::',2), regexp_replace(question_latex,'\s+',' ','g'), correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND source_reference LIKE %s ORDER BY id", (tb + "%",))
R = c.fetchall(); random.Random(seed).shuffle(R)
for i, (t, loc, q, k, d) in enumerate(R[:n]):
    print(f"{i}. {t} [{loc}] Q: {q[:330]}\n   K: {k} | D: {[str(x.get('value'))[:45] for x in d or []]}")
