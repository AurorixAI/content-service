import random, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id FROM tasks_master WHERE is_active ORDER BY id")
ids = [r[0] for r in c.fetchall()]
prev = set(json.load(open("/audit/ctrl300_ids.json"))) | set(json.load(open("/audit/ctrl_todo.json")))
pool = [t for t in ids if t not in prev]
random.Random(20260926).shuffle(pool)
json.dump(pool[:300], open("/audit/ctrl3_todo.json", "w"))
print("active", len(ids), "excluded prev", len(prev), "sample", 300)
