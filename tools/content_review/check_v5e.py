import json, re, psycopg2
from fractions import Fraction as F
P = json.load(open("/audit/v5e_P.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
def ev(s):
    s = s.replace("{,}", ".").replace("\\left", "").replace("\\right", "").replace(" ", "")
    s = re.sub(r"(\d+)\\dfrac\{(\d+)\}\{(\d+)\}", r"(F(\1)+F(\2,\3))", s)
    s = re.sub(r"\\dfrac\{(-?\d+)\}\{(\d+)\}", r"F(\1,\2)", s)
    s = s.replace("\\cdot", "*").replace(":", "/")
    s = re.sub(r"(?<![\w(,])(\d+\.\d+|\d+)(?![\w.,)]|\))", r"F('\1')", s)
    return F(eval(s, {"F": F}))
def key(k):
    k = re.sub(r"[\s$]", "", k)
    m = re.fullmatch(r"(-?\d+)\\dfrac\{(\d+)\}\{(\d+)\}", k)
    if m: return F(int(m.group(1))) + F(int(m.group(2)), int(m.group(3)))
    return ev(k)
ok = bad = skip = 0
for t, e in P.items():
    c.execute("SELECT correct_answer_latex FROM tasks_master WHERE id=%s", (t,)); k = e.get("k") or c.fetchone()[0]
    if not re.match(r"(Найдите (сумму|разность|значение (выражения|разности))|Вычислите)", e["q"]): skip += 1; continue
    expr = re.findall(r"\$([^$]+)\$", e["q"])[-1] if "2 :" not in e["q"] else re.findall(r"\$([^$]+)\$", e["q"])[0]
    try:
        v, kv = ev(expr), key(k)
        if v == kv: ok += 1
        else: bad += 1; print("BAD", t, expr, v, k)
    except Exception as ex: skip += 1; print("SKIP", t, expr, ex)
print("ok", ok, "bad", bad, "skip(checked by hand)", skip)
