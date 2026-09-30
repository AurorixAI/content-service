import psycopg2, json
from collections import Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name='tasks_master' ORDER BY ordinal_position")
cols = c.fetchall(); print([(a, b[:10], n, (d or "")[:25]) for a, b, n, d in cols])
names = [x[0] for x in cols]
for pref in ["GEN_%", "ds_llm_%", "DIFF_%"]:
    c.execute("SELECT * FROM tasks_master WHERE is_active AND id LIKE %s ORDER BY updated_at DESC LIMIT 1", (pref,))
    r = dict(zip(names, c.fetchone()))
    print("=====", pref); print(json.dumps({k: (str(v)[:160]) for k, v in r.items()}, ensure_ascii=False, indent=0))
c.execute("SELECT split_part(id,'_',1), source_type, verification_status, count(*) FROM tasks_master WHERE is_active GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 15"); print(c.fetchall())
