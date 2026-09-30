import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT split_part(source_reference,'::',1) b, split_part(id,'_',1)||'_'||split_part(id,'_',2) p, count(*) FROM tasks_master WHERE is_active AND id LIKE 'G5_%%' OR is_active AND id LIKE 'G6_%%' GROUP BY 1,2 ORDER BY 2,3 DESC""")
for r in c.fetchall(): print(r)
c.execute("SELECT id, source_reference FROM tasks_master WHERE id IN ('G5_TB_63_1498.9','G5_TB_44_1738.7','G5_TB_4_67.1','G5_TB_24_946.1')"); print(c.fetchall())
c.execute("SELECT id, title, file_path FROM textbooks") if False else None
c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"); print([r[0] for r in c.fetchall()])
