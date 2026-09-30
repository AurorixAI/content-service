import random, json, psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id FROM tasks_master WHERE is_active ORDER BY id")
ids = [r[0] for r in c.fetchall()]
prev=set()
for f in ["ctrl300_ids","ctrl_todo","ctrl3_todo","sample100_ids","ctrl4_todo","ctrl5_todo","ctrl6_todo","ctrl7_todo","ctrl8_todo","ctrl9_todo","ctrl10_todo","ctrl11_todo"]:
    prev|=set(json.load(open(f"/audit/{f}.json")))
sp=json.load(open("/audit/sample300_spec.json")); prev|=set(sp if isinstance(sp,list) else sp.keys())
def hi(i): return re.match(r'^(?:GEN_)?G(?:9|10|11)_',i) is not None
q=[i for i in ids if hi(i) and i not in prev]
# order: family-contiguous by id
json.dump(q, open("/audit/rq_todo.json","w"))
print(len(q), "of", sum(1 for i in ids if hi(i)))
