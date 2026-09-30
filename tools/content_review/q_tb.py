import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT * FROM textbooks WHERE textbook_id::text='184640af-64e7-47af-a974-8b8112e6ffb2'")
cols=[d[0] for d in c.description]
for r in c.fetchall(): print({k:v for k,v in zip(cols,r) if v is not None and k not in ('content',)})
