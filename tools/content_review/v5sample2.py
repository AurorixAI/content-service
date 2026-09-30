import json, random, psycopg2, re
exec(open("/audit/tb_answers.py").read().split("db = psycopg2.connect")[0].replace("book = sys.argv[1]", "book = 'vilenkin5'"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, source_reference, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND source_reference LIKE %s", (tbid + "%",))
rows = c.fetchall(); un = []
for tid, src, q, k, d in rows:
    ex, it = locate(tid, src); a = ANS.get(ex or "")
    if a and ((a.get(it) if it else (a.get("") or (list(a.values())[0] if len(a)==1 else None))) is not None): continue
    un.append((tid, src, q, k, d))
print("total", len(rows), "uncovered", len(un))
random.Random(20260926).shuffle(un)
out = []
for tid, src, q, k, d in [u for u in un if u[0] not in set(x["id"] for x in json.load(open("/audit/v5sample.json")))][:40]:
    out.append({"id": tid, "src": src.split("::",1)[-1], "q": " ".join(q.split()), "k": k, "d": [x.get("value") for x in (d or [])]})
json.dump(out, open("/audit/v5sample2.json", "w"), ensure_ascii=False, indent=1)
for i, r in enumerate(out): print(i, r["id"], "|", r["src"], "\n Q:", r["q"][:400], "\n K:", r["k"], "| D:", r["d"])
