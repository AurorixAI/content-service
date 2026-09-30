import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute(r"SELECT id, is_active, skill_id, regexp_replace(question_latex,'\s+',' ','g'), correct_answer_latex FROM tasks_master WHERE id ~ '^G5_TB_64_15(21|28|36|44|48|56)' ORDER BY id")
for r in c.fetchall(): print(r[0], "A" if r[1] else "-", r[2], "|", r[3][-75:], "| K:", r[4])
