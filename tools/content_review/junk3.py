import psycopg2, json
j = json.load(open("/audit/junk2.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in sorted(j["junk"]):
    c.execute("SELECT question_latex, question_text, correct_answer_latex, distractor_meta FROM tasks_master WHERE id=%s", (t,)); q, qt, k, d = c.fetchone()
    v = j["junk"][t]
    print("##", t, "| K:", k, "| Q:", " ".join(q.split())[:170])
    if q != qt: print("   RAW:", " ".join((qt or '').split())[:170])
    print("   D:", [("X " if i in v["drop"] else "") + str(x.get("value"))[:45] for i, x in enumerate(d)])
