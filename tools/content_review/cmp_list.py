import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, correct_answer FROM tasks_master WHERE is_active")
n = 0; import random; rows = []
for tid, q, k, ka in c.fetchall():
    key = re.sub(r"[\s$]", "", k or ka or "")
    if key in ("<", ">", "=", "\\lt", "\\gt", "\\le", "\\ge", "\\leq", "\\geq", "≤", "≥", "\\ne", "\\neq") or re.fullmatch(r"[<>=]|больше|меньше|равны", key): rows.append((tid, key, " ".join((q or "").split())[-140:]))
print(len(rows))
from collections import Counter; print(Counter(r[1] for r in rows)); print(Counter(r[0].split("_")[0] + r[0].split("_")[1] for r in rows))
random.Random(1).shuffle(rows)
for r in rows[:40]: print(r)
