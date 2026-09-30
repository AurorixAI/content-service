import psycopg2
from collections import Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT level, count(*) FROM knowledge_hierarchy WHERE is_active GROUP BY 1 ORDER BY 1"); print("levels:", c.fetchall())
c.execute("SELECT max(level) FROM knowledge_hierarchy"); L = c.fetchone()[0]
c.execute("""SELECT k.id, k.class_level_start, count(t.id) FROM knowledge_hierarchy k LEFT JOIN tasks_master t ON t.skill_id=k.id AND t.is_active
             WHERE k.is_active AND k.level=%s GROUP BY 1,2""", (L,))
rows = c.fetchall()
z = [r for r in rows if r[2] == 0]; low = [r for r in rows if 0 < r[2] < 3]
print("atomic level", L, "skills", len(rows), "with 0 tasks", len(z), "with 1-2 tasks", len(low))
print("zero by grade:", sorted(Counter(r[1] for r in z).items(), key=lambda x: (x[0] is None, x[0] or 0)))
