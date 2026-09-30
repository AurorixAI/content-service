import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
P = re.compile(r"\$([^$]*\d)\$,\s*\$(\d[^$]*)\$")
EX = re.compile(r"систем|выборк|ряд[ау]?\b|ряда|таблиц|чис(ла|ел)[:\s]|решени[яй] сист|медиан|мод[уы]|значени[йя] случ|распределени|A\)|A\.|\$A|примерам|значениям|звёздоч|звездоч|частот|промежут|дроб(и|ей)[:\s]|точк|координат|функци[яи] от|вершин|корн", re.I)
for t, q, k in c.fetchall():
    q = q or ""
    for m in P.finditer(q):
        if EX.search(q): break
        a, b = m.group(1), m.group(2)
        if re.search(r"[+\-:=]|\\cdot|[a-z]", a[-8:] + b[:8]) or re.fullmatch(r"\d+", a):
            print(t, "|", " ".join(q.split())[-95:], "| K:", (k or "")[:45]); break
