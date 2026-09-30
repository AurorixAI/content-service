import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT split_part(skill_id,'_',1), difficulty, count(*) FROM tasks_master WHERE is_active AND tags->>'generated_by'='claude-manual-2026-09-26' GROUP BY 1,2 ORDER BY 1,2"); r = c.fetchall()
print(r, "total", sum(x[2] for x in r))
