import json, psycopg2
ids = json.load(open("/audit/knio_ids.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for grp in ("n5", "n3"):
    c.execute("SELECT id, source_reference, question_latex, correct_answer, answer_options, distractor_meta FROM tasks_master WHERE id = ANY(%s) ORDER BY id", (ids[grp],))
    for tid, src, q, ca, ao, dm in c.fetchall():
        print(f"### [{grp}] {tid} src={src.split('::',1)[-1] if src else ''}")
        print("Q:", " ".join(q.split())[:400])
        print("K:", ca[:300])
        for o in ao: print("  O:", (o.get("text") if isinstance(o, dict) else o)[:200])
        for d in dm or []:
            if isinstance(d, dict): print("  D:", str(d.get("value"))[:200])
