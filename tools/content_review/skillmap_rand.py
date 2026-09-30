import random, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT t.id, regexp_replace(t.question_latex,'\s+',' ','g'), k.id, gp.name_ru||' → '||p.name_ru||' → '||k.name_ru
             FROM tasks_master t JOIN knowledge_hierarchy k ON k.id=t.skill_id JOIN knowledge_hierarchy p ON p.id=k.parent_id JOIN knowledge_hierarchy gp ON gp.id=p.parent_id
             WHERE t.is_active ORDER BY t.id""")
R = c.fetchall(); random.Random(9261).shuffle(R)
for i, r in enumerate(R[:40]): print(f"{i}. {r[0]} | {r[1][:120]}\n   SKILL: {r[2]} {r[3]}")
