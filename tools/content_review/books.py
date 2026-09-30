import psycopg2, collections
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT b.title, split_part(t.source_reference,'::',1), count(*), min(split_part(t.source_reference,'::',2)), max(split_part(t.source_reference,'::',2))
             FROM tasks_master t LEFT JOIN textbooks b ON b.textbook_id::text = split_part(t.source_reference,'::',1)
             WHERE t.is_active GROUP BY 1,2 ORDER BY 3 DESC""")
for r in c.fetchall(): print(f"{r[2]:6d} | {r[0]} | {(r[1] or '')[:8]} | {r[3]} .. {r[4]}")
