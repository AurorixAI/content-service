import json, psycopg2
P = json.load(open("/audit/dup_plan.json")); D = json.load(open("/audit/deact_dups.json"))
keeps = {p["keep"] for p in P}
print("keep∩drop:", keeps & set(D))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT count(*) FROM tasks_master WHERE is_active AND id = ANY(%s)", (list(keeps),)); print("keeps active:", c.fetchone()[0], "of", len(keeps))
c.execute("SELECT count(*) FROM tasks_master WHERE is_active AND id = ANY(%s)", (list(D),)); print("drops active:", c.fetchone()[0], "of", len(D))
