import sys, psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
sec = sys.argv[1]
c.execute("SELECT id, source_reference, question_latex, correct_answer_latex FROM tasks_master WHERE is_active AND source_reference LIKE %s", ("1b758c3d%%::" + sec + ":%%",))
rows = c.fetchall()
def k(r):
    loc = r[1].split(":")[-1]
    return [int(x) if x.isdigit() else 0 for x in re.split(r"[.]", loc)]
for tid, src, q, key in sorted(rows, key=k):
    q = " ".join(q.split()); q = re.sub(r"^(Найдите производную функции|Решите уравнение|Решите неравенство|Вычислите)[:.]?\s*", "", q)
    print(src.split(":")[-1], "|", q[:int(sys.argv[2]) if len(sys.argv) > 2 else 150], "| K:", " ".join((key or "").split())[:110])
