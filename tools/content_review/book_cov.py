import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT coalesce(split_part(t.source_reference,'::',1),'—'), coalesce(b.display_name, b.title, ''), count(*) FROM tasks_master t
             LEFT JOIN textbooks b ON b.textbook_id::text = split_part(t.source_reference,'::',1) WHERE t.is_active GROUP BY 1,2 ORDER BY 3 DESC""")
for r in c.fetchall(): print(r[0][:8], "|", r[1][:60], "|", r[2])
c.execute("SELECT count(*), count(*) FILTER (WHERE source_reference IS NULL) FROM tasks_master WHERE is_active"); print("total active, without source:", c.fetchone())
