import json, psycopg2
ids = json.load(open("/audit/knio_ids.json"))["n5"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
cols = ["id","source_reference","answer_type","correct_answer","correct_answer_latex","answer_options","answer_options_latex","distractor_meta","tags"]
c.execute(f"SELECT {','.join(cols)} FROM tasks_master WHERE id = ANY(%s) ORDER BY id", (ids,))
out = []
for r in c.fetchall():
    t = dict(zip(cols, r)); tg = t.pop("tags") or {}
    t["repairs"] = sorted(k for k in tg if k.startswith("content_repair::"))
    out.append(t)
json.dump(out, open("/audit/knio_full.json","w"), ensure_ascii=False, indent=1)
print(len(out))
