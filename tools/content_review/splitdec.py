import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
# math segment ending with a digit, then ", " then a math segment starting with a digit, and the segments contain operators (expression split, not a list)
P = re.compile(r"\$([^$]*[+\-·\\a-z(][^$]*\d)\$,\s*\$(\d[^$]*)\$")
n = 0
for t, q, k in c.fetchall():
    m = P.search(q or "")
    if m and re.search(r"[+\-]|\\cdot", m.group(2) + m.group(1)[-6:]):
        n += 1; print(t, "|", " ".join(q.split())[-100:], "| K:", (k or "")[:40])
print(n)
