import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute(r"SELECT id, correct_answer_latex FROM tasks_master WHERE is_active AND (correct_answer_latex ~ '\\d?frac\{\s*\}\{\s*\}' OR correct_answer_latex ~ '^\$?\s*\$?$')")
print(c.fetchall())
