import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
q = lambda s: (c.execute(s), c.fetchall())[1]
print("active/inactive:", q("SELECT count(*) FILTER (WHERE is_active), count(*) FILTER (WHERE NOT is_active) FROM tasks_master"))
print("inactive with reason:", q("SELECT count(*) FROM tasks_master WHERE NOT is_active AND tags ? 'deactivated_reason'"))
print("touched by content_repair batches:", q("SELECT count(*) FROM tasks_master WHERE tags::text LIKE '%content_repair%' OR tags::text LIKE '%manual-review%'"))
