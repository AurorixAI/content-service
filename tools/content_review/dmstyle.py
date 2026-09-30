import psycopg2, json
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
for t in ["G7_ALG_22_7.2", "G6_TB_6_249.1", "G5_TB_1_10.2"]:
    c.execute("SELECT distractor_meta FROM tasks_master WHERE id=%s", (t,)); r = c.fetchone()
    if r: print(t, json.dumps((r[0] or [])[:1], ensure_ascii=False)[:700])
