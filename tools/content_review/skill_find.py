import psycopg2, sys
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for pat in sys.argv[1:]:
    g, w = pat.split(":")
    c.execute("""SELECT k.id, k.name_ru, p.name_ru, (SELECT count(*) FROM tasks_master t WHERE t.skill_id=k.id AND t.is_active)
                 FROM knowledge_hierarchy k JOIN knowledge_hierarchy p ON p.id=k.parent_id WHERE k.level='L4' AND k.is_active AND k.id LIKE %s AND (k.name_ru ILIKE %s OR p.name_ru ILIKE %s OR k.description ILIKE %s)""",
              (g + "%", "%" + w + "%", "%" + w + "%", "%" + w + "%"))
    print(pat, c.fetchall()[:8])
