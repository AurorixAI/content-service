import json, os, re, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
H = json.load(open("/audit/tail_hits.json"))
for gi, (b, n, tail, miss) in enumerate(H):
    c.execute("SELECT id, regexp_replace(question_latex,'\s+',' ','g'), correct_answer_latex FROM tasks_master WHERE is_active AND id ~ %s ORDER BY id", ("^" + re.escape(b) + r"\.\d+$",))
    R = c.fetchall(); stem = os.path.commonprefix([q for _, q, _ in R])
    print(f"#{gi} {b} STEM: {stem[-90:]}")
    for t, q, k in R: print(f"   .{t.rsplit('.',1)[1]}: {q[len(stem):][:150]} || K: {(k or '')[:60]}")
