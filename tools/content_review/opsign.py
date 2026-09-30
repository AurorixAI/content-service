import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND (question_latex ~* 'знак (действия|умножения|арифметич)' OR question_latex ~* 'вместо клет' ) ORDER BY id")
for t, q, k, d in c.fetchall():
    print(t, "| K:", k, "|", " ".join(q.split())[-90:], "| D:", [str(x.get("value"))[:25] for x in d or []])
