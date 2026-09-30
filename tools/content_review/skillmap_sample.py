import json, random, psycopg2
R = json.load(open("/audit/skillmap_candidates.json"))
strong = [r for r in R if r["rel"] == "other_L2" and r["rank"] >= 10 and r["s_best"] - r["s_own"] > 0.15]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT k.id, k.name_ru, p.name_ru, gp.name_ru FROM knowledge_hierarchy k JOIN knowledge_hierarchy p ON p.id=k.parent_id JOIN knowledge_hierarchy gp ON gp.id=p.parent_id")
N = {r[0]: f"{r[3]} → {r[2]} → {r[1]}" for r in c.fetchall()}
random.Random(26).shuffle(strong)
for i, r in enumerate(strong[:40]):
    print(f"{i}. {r['id']} | {r['q'][:130]}\n   OWN : {r['own']} {N.get(r['own'],'')}\n   BEST: {r['best']} {N.get(r['best'],'')}")
