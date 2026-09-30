import json, sys, psycopg2
b, lo, hi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
d = json.load(open(f"/audit/tba_{b}.json")); L = d["mismatch"] + d["differ"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for i, r in enumerate(L[lo:hi], lo):
    c.execute("SELECT question_latex, correct_answer_latex, is_active FROM tasks_master WHERE id=%s", (r["id"],)); q, k, a = c.fetchone()
    if not a: continue
    print(f"#{i}", r["id"], "\n Q:", " ".join(q.split())[:260], "\n K:", k[:160], "\n B:", r["book"][:140].replace("\n", " "))
