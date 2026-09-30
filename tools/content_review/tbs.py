import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='textbooks'"); cols=[r[0] for r in c.fetchall()]; print(cols)
c.execute("SELECT textbook_id,title,authors,class_level,edition,total_pages,display_name FROM textbooks WHERE textbook_id::text IN ('47167115-5961-4405-bb55-1bda8ce1b687','5630a994-061d-4c20-9863-fe049c8059fb','a7585f33-4f43-47b2-8ca6-c4ef6c8020c8','184640af-64e7-47af-a974-8b8112e6ffb2')")
for r in c.fetchall(): print({k:(str(v)[:90]) for k,v in zip(["id","title","authors","cl","ed","pages","dn"],r) if v is not None})
