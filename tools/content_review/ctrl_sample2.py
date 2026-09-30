import sys, random, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id FROM tasks_master WHERE is_active OR id = 'G9_TB_6_83_1' ORDER BY id")
ids = [r[0] for r in c.fetchall()]; random.Random(260926).shuffle(ids)
orig = ids[:300]
json.dump(orig, open("/audit/ctrl300_orig.json", "w"))
# the shifted permutation used for chunk 150-199 (active set without 6_83_1)
c.execute("SELECT id FROM tasks_master WHERE is_active ORDER BY id"); ids2 = [r[0] for r in c.fetchall()]; random.Random(260926).shuffle(ids2)
reviewed = set(orig[:150]) | set(ids2[150:200])
extra = [t for t in orig[150:] if t not in reviewed]
print("reviewed distinct:", len(reviewed), "remaining in original 300:", len(extra))
need = 300 - len(reviewed)
# take remaining from the original list, then continue further down the original permutation if needed
pool = [t for t in ids if t not in reviewed]
todo = pool[:need]
json.dump(todo, open("/audit/ctrl_todo.json", "w")); print("todo", len(todo))
