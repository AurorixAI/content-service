import json, psycopg2, sys
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='textbook_toc'"); print([r[0] for r in c.fetchall()])
G = json.load(open("/audit/dup_located.json"))
ids = [x["id"] for g in G if g["book"].startswith(sys.argv[1]) for x in g["items"]][:int(sys.argv[2])]
c.execute("""SELECT t.id, t.skill_id, k.name_ru, t.toc_id, toc.title FROM tasks_master t LEFT JOIN knowledge_hierarchy k ON k.id=t.skill_id
             LEFT JOIN textbook_toc toc ON toc.id=t.toc_id WHERE t.id = ANY(%s)""", (ids,))
for r in c.fetchall(): print(r[0], "|", r[1], (r[2] or "")[:45], "| toc:", r[3], (r[4] or "")[:50])
