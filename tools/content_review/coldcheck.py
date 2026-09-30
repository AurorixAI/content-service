import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute(r"SELECT id, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND distractor_meta::text ~ '\"value\": \"None\"'")
print([r[0] for r in c.fetchall()])
