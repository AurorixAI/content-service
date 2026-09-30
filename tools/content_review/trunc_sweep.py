import re, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
for t, q, k in c.fetchall():
    k0 = (k or "").strip().strip("$").strip()
    if len(k0) < 3: continue
    # key cut right before a decimal comma / unbalanced brackets
    bal = k0.count("(") - k0.count(")") + k0.count("[") - k0.count("]")
    cut = (k0 + "{,}") in (q or "")
    br = k0.count("{") != k0.count("}")
    if cut or br or re.search(r"\\sqrt\{0\}|\{\s*\}\s*$", k0) or (bal > 0 and not re.search(r"[\[(][^\])]*;\s*\+?\\infty", k0) and "∪" not in k0 and "\\cup" not in k0 and not re.search(r"\[.*\)|\(.*\]", k0)):
        print(t, "|", k[:120])
