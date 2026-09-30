# Bank-wide check of comparison tasks (key <, >, =): recompute the sign from the two compared expressions.
import psycopg2, re, json
from fractions import Fraction as F
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, correct_answer, source_reference FROM tasks_master WHERE is_active")
def ev(s):
    s = s.strip().rstrip(";.,?").strip()
    s = s.replace("{,}", ".").replace("\\,", "").replace("\\left", "").replace("\\right", "").replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    if re.search(r"[a-zA-Zа-яА-Я]", re.sub(r"\\(frac|cdot|div)", "", s)): raise ValueError
    s = re.sub(r"(\d+)\s*\\frac\{(\d+)\}\{(\d+)\}", r"(F(\1)+F(\2,\3))", s)       # mixed number
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(F(\1)/F(\2))", s)
    s = s.replace("\\cdot", "*").replace("\\div", "/").replace(":", "/").replace("−", "-")
    s = re.sub(r"\|([^|]+)\|", r"abs(\1)", s)
    s = re.sub(r"\^\{?(\d+)\}?", r"**\1", s)
    s = re.sub(r"(?<![\w.])(\d+\.\d+|\d+)(?![\w.(])", r"F('\1')", s)
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    if re.search(r"[{}\\]", s): raise ValueError
    return F(eval(s, {"F": F, "abs": abs}))
out, n = [], 0
for tid, q, k, ka, src in c.fetchall():
    key = re.sub(r"[\s$]", "", k or ka or "")
    if key not in ("<", ">", "="): continue
    q = q or ""
    segs = re.findall(r"\$([^$]+)\$", q)
    A = B = None
    m = re.search(r"\$([^$]+)\$\s*(?:\S{1,4}\s*)?и\s*\$([^$]+)\$\s*(?:\S{1,4})?\s*[;.?]?\s*$", q)
    if m: A, B = m.group(1), m.group(2)
    elif segs and re.search(r"\\ast|\*|\\square|\?", segs[-1]):
        p = re.split(r"\\ast|\*|\\square|\(\?\)|\?", segs[-1])
        if len(p) == 2: A, B = p
    if A is None: continue
    try: a, b = ev(A), ev(B)
    except Exception: continue
    n += 1
    true = "<" if a < b else ">" if a > b else "="
    if true != key: out.append((tid, key, true, " ".join(q.split())[-150:], src[:8]))
print("checked", n, "mismatch", len(out))
for r in out: print(r)
json.dump(out, open("/audit/cmp_mismatch.json", "w"), ensure_ascii=False, indent=0)
