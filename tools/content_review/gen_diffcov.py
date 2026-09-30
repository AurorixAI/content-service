import psycopg2, json
S = [s["id"] for s in json.load(open("/audit/skills_low.json"))]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT skill_id, count(*), string_agg(DISTINCT difficulty, '') FROM tasks_master WHERE is_active AND skill_id = ANY(%s) GROUP BY 1", (S,))
r = c.fetchall(); print("81 skills now: min tasks", min(x[1] for x in r), "| skills with ≥2 difficulty levels:", sum(1 for x in r if len(set(x[2])) >= 2), "of", len(r))
c.execute("SELECT count(*) FROM tasks_master WHERE is_active AND tags->>'generated_by'='claude-manual-2026-09-26'"); print("new tasks active:", c.fetchone()[0])
