import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in ["G9_TB_13_206_1","G9_TB_27_322_1"]:
    c.execute("SELECT t.id, b.title, t.source_reference FROM tasks_master t LEFT JOIN textbooks b ON b.textbook_id::text = split_part(t.source_reference,'::',1) WHERE t.id=%s", (t,)); print(c.fetchone())
