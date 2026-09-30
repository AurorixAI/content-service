import re, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
R = {"placeholder": [], "garbled_key": [], "key_in_question": []}
nrm = lambda s: re.sub(r"\s|\$|\\left|\\right|\{,\}", "", s or "").replace("\\dfrac", "\\frac")
for t, q, k in c.fetchall():
    q, k = q or "", k or ""
    if re.search(r"отсутствует упражнени|обратитесь к соответствующей|Результаты вычислений|не удалось распознать|текст (задания|условия) отсутств", q + " " + k, re.I):
        R["placeholder"].append((t, q[:150], k[:80]))
    if re.fullmatch(r"\s*\$\s*\(\s*-?[\d.,{}]*\s*\)\s*\$\s*", k) or k.strip() in ("$$", "", "$\\,$"):
        R["garbled_key"].append((t, q[:150], k))
    nk = nrm(k)
    if len(nk) >= 12 and "=" not in nk and nk in nrm(q) and re.search(r"Разложите|Упростите|Сократите|Вынес", q):
        R["key_in_question"].append((t, q[:150], k[:100]))
json.dump(R, open("/audit/class_scan.json", "w"), ensure_ascii=False, indent=1)
print({x: len(y) for x, y in R.items()})
