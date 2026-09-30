import random, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id FROM tasks_master WHERE is_active ORDER BY id")
ids = [r[0] for r in c.fetchall()]
prev=set()
for f in ["ctrl300_ids","ctrl_todo","ctrl3_todo","sample100_ids","ctrl4_todo","ctrl5_todo"]:
    prev|=set(json.load(open(f"/audit/{f}.json")))
sp=json.load(open("/audit/sample300_spec.json")); prev|=set(sp if isinstance(sp,list) else sp.keys())
pool = [t for t in ids if t not in prev]
random.Random(20261001).shuffle(pool)
json.dump(pool[:300], open("/audit/ctrl6_todo.json", "w"))
print("active", len(ids), "excluded prev", len(prev), "sample", 300)
