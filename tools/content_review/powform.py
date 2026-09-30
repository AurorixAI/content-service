import psycopg2, re
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active AND question_latex ~* '(в виде (степени|произведения)|запишите (в виде|с помощью) степен)' ORDER BY id")
rows = c.fetchall(); print(len(rows))
for t, q, k in rows:
    kk = re.sub(r"[\s$]", "", k or "")
    want_pow = re.search(r"в виде степени|с помощью степен|в виде степен", q, re.I) is not None and "произведения степень" not in q
    flag = ""
    if want_pow and "^" not in kk: flag = "NO-POWER"
    if "в виде произведения" in q and "^" in kk and "\\cdot" not in kk and ")(" not in kk: flag = "NO-PRODUCT"
    if "в виде произведения" in q and re.fullmatch(r"[\d\\,]+", kk): flag = "NUMERIC"
    if flag: print(flag, t, "|", " ".join(q.split())[-80:], "| K:", k)
