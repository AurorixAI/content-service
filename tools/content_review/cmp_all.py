import psycopg2, re
from fractions import Fraction as F
exec(open("/audit/cmp_verify.py").read().split("out, n = [], 0")[0].split('c.execute(')[0])
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, correct_answer, distractor_meta FROM tasks_master WHERE is_active ORDER BY id")
U = {"т": 1000000, "ц": 100000, "кг": 1000, "г": 1, "га": 10000, "а": 100, "м$^{2}$": 1, "л": 1000, "см$^{3}$": 1, "см$^3$": 1, "км": 100000, "м": 100, "дм": 10, "см": 1, "мм": F(1, 10), "ч": 60, "мин": 1}
def val(seg, after):
    v = ev(seg); m = re.match(r"\s*(см\$\^\{?3\}?\$|м\$\^\{?2\}?\$|т|ц|кг|г|га|а|л|км|м|дм|см|мм|ч|мин)(?![а-яё])", after)
    return v * F(U.get(m.group(1).replace("{3}", "3").replace("^3", "^{3}") if m else "", U.get(m.group(1), 1) if m else 1)) if m else v, (m.group(1) if m else "")
for tid, q, k, ka, d in c.fetchall():
    key = re.sub(r"[\s$]", "", k or ka or "")
    if key not in ("<", ">", "=", "равны"): continue
    q = q or ""; res = "?"
    try:
        m = list(re.finditer(r"\$([^$]+)\$([^$]{0,12}?)\s*и\s*\$([^$]+)\$([^$]{0,10})", q))
        if m:
            m = m[-1]; a, ua = val(m.group(1), m.group(2)); b, ub = val(m.group(3), m.group(4))
        else:
            seg = re.findall(r"\$([^$]+)\$", q)[-1]
            p = re.split(r"\\ast|\*|\\square|\(\?\)|\?|\\cdot|\.\.\.", seg)
            if len(p) != 2: raise ValueError
            a, b = ev(p[0]), ev(p[1])
        res = "<" if a < b else ">" if a > b else "="
    except Exception: pass
    flag = "OK " if res == key else ("?? " if res == "?" else "XX ")
    print(flag, tid, key, "calc", res, "|", " ".join(q.split())[-120:])
