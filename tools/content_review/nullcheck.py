import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT id, jsonb_array_length(distractor_meta), (SELECT count(*) FROM jsonb_array_elements(distractor_meta) e WHERE e->>'value' IS NULL OR e->>'value' IN ('', 'None', 'null')) FROM tasks_master
             WHERE is_active AND EXISTS (SELECT 1 FROM jsonb_array_elements(distractor_meta) e WHERE e->>'value' IS NULL OR e->>'value' IN ('', 'None', 'null'))""")
R = c.fetchall(); print(len(R), R[:30])
