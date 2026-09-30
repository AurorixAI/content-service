import psycopg2, json
from collections import Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT k.id, k.name_ru, k.description, k.class_level_start, k.difficulty_level, k.example_task, k.assessed_ability, k.formula, k.parent_id,
                    count(t.id) FILTER (WHERE t.is_active), count(t.id) FILTER (WHERE NOT t.is_active)
             FROM knowledge_hierarchy k LEFT JOIN tasks_master t ON t.skill_id=k.id
             WHERE k.is_active AND k.level='L4' GROUP BY k.id ORDER BY 10, 1""")
rows = c.fetchall()
dist = Counter(min(r[9], 10) for r in rows); print("tasks-per-skill distribution (10 = 10+):", sorted(dist.items()))
low = [r for r in rows if r[9] < 3]
json.dump([dict(id=r[0], name=r[1], desc=r[2], grade=r[3], diff=r[4], example=r[5], ability=r[6], formula=r[7], parent=r[8], active=r[9], inactive=r[10]) for r in low], open("/audit/skills_low.json", "w"), ensure_ascii=False, indent=1)
print("skills <3 active:", len(low), Counter(r[9] for r in low), "by grade", sorted(Counter(r[3] for r in low).items()))
for r in low[:12]: print(r[0], r[9], "(inactive", r[10], ")", "|", r[1], "|", (r[2] or "")[:80])
