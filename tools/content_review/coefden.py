import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, regexp_replace(question_latex,'\s+',' ','g'), correct_answer_latex FROM tasks_master WHERE is_active AND question_latex ~ '\\\\dfrac\\{-?\\d+\\}\\{\\d+[a-z]\\}' AND question_latex ~* '(линейн|график|прям|y *=)'")
for r in c.fetchall(): print(r[0], "|", r[1][-140:], "| K:", (r[2] or "")[:50])
