import json, re
from fractions import Fraction as F
R = json.load(open("/audit/restore_J_v5b.json"))
import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
U = {"т": 10**6, "ц": 10**5, "кг": 1000, "г": 1, "га": 10**6, "а": 10**4, "л": 1000, "см$^{3}$": 1, "м": 100, "см": 1}
def ev(s):
    s = s.strip().rstrip(";.,?").strip().replace("{,}", ".").replace("\\,", "").replace("\\dfrac", "\\frac")
    s = re.sub(r"(\d+)\s*\\frac\{(\d+)\}\{(\d+)\}", r"(F(\1)+F(\2,\3))", s)
    s = re.sub(r"-\(F\((\d+)\)\+", r"-(F(\1)+", s)
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(F(\1)/F(\2))", s)
    s = s.replace("\\cdot", "*").replace(":", "/")
    s = re.sub(r"\|([^|]+)\|", r"abs(\1)", s)
    s = re.sub(r"(?<![\w.(])(\d+\.\d+|\d+)(?![\w.])", r"F('\1')", s)
    s = s.replace("F('F('", "F(").replace(")/F(", ")/F(")
    return F(eval(s, {"F": F, "abs": abs}))
def mixfix(s):  # «2\dfrac{4}{9}» inside larger expr handled by regex above; negative mixed: -2\dfrac{5}{9} -> -(2+5/9)
    return re.sub(r"-(\d+)\\dfrac\{(\d+)\}\{(\d+)\}", r"-(\1\\dfrac{\2}{\3})", s)
bad = []; few = []
for t, s in R.items():
    c.execute("SELECT question_latex, correct_answer_latex, distractor_meta FROM tasks_master WHERE id=%s", (t,)); q0, k0, d0 = c.fetchone()
    f = s["fields"]; q = f.get("question_latex", q0); k = f.get("correct_answer_latex", k0); d = f.get("distractor_meta", d0)
    key = re.sub(r"[\s$]", "", k or "")
    vals = [str(x.get("value")) for x in d]
    if len(vals) < 2: few.append((t, vals))
    if key in "<>=" and key:
        segs = re.findall(r"\$([^$]+)\$", q)
        try:
            m = re.search(r"\$([^$]+)\$\s*([а-яё$^{}3]*)\s*и\s*\$([^$]+)\$\s*([а-яё$^{}3]*)", q)
            if m and not re.search(r"\\ast", q):
                a, b = ev(mixfix(m.group(1))), ev(mixfix(m.group(3)))
                ua, ub = m.group(2).strip(), m.group(4).strip()
                if ua or ub: a, b = a * U.get(ua, 1), b * U.get(ub, 1)
            else:
                seg = [x for x in segs if "\\ast" in x][-1]; p = seg.split("\\ast")
                a, b = ev(mixfix(p[0])), ev(mixfix(p[1]))
            tr = "<" if a < b else ">" if a > b else "="
            if tr != key: bad.append((t, key, tr, q[-90:]))
        except Exception as ex: bad.append((t, key, "PARSE " + str(ex)[:40], q[-90:]))
        for v in vals:
            if re.sub(r"[\s$]", "", v) in ({key} | ({"≥", "\\geq", ">="} if key == ">" else {"≤", "\\leq", "<="} if key == "<" else set())): bad.append((t, "dup-key distractor", v))
print("tasks", len(R), "issues", len(bad)); [print(" ", b) for b in bad]
print("<2 distractors:", few)
