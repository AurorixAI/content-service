import json, sys, psycopg2
ids = sys.argv[1].split(",")
r = {x["id"]: x for b in ("merzlyak10",) for x in json.load(open(f"/audit/tba_{b}.json"))["mismatch"] + json.load(open(f"/audit/tba_{b}.json"))["differ"]}
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in ids:
    c.execute("SELECT question_latex, correct_answer_latex FROM tasks_master WHERE id=%s", (t,)); q, k = c.fetchone()
    print("##", t, "\n Q:", " ".join(q.split())[:400], "\n K:", k[:300], "\n B:", r.get(t, {}).get("book", "")[:200].replace("\n", " "))
