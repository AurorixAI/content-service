# distractor whose numeric content (multiset of numbers incl. fractions, signs) equals the key's
import re, json, psycopg2
from fractions import Fraction as F
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND distractor_meta IS NOT NULL")
def norm(s):
    s = s or ""
    s = re.sub(r"\\[dt]?frac\{(-?[\d.,]+)\}\{([\d.,]+)\}", r" \1/\2 ", s)
    s = re.sub(r"(\d)\{,\}(\d)", r"\1.\2", s); s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    s = s.replace("−", "-").replace("\\left", "").replace("\\right", "")
    return s
def nums(s):
    s = norm(s); out = []
    for m in re.finditer(r"(-?)\s*(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?", s):
        den = F(m.group(3)) if m.group(3) else F(1)
        v = F(m.group(2)) / den if den else F(10**9)
        out.append(-v if m.group(1) else v)
    return out
def skel(s):  # non-numeric skeleton: brackets & words
    s = norm(s); s = re.sub(r"\\geq?\b", "≥", s); s = re.sub(r"\\leq?\b", "≤", s); s = s.replace("\\ne ", "≠").replace("\\neq", "≠")
    s = re.sub(r"\\(dfrac|frac|tfrac|operatorname|text|mathrm|ldots|dots|cdot|times|quad|,|;|!| )", lambda m: "·" if m.group(1) in ("cdot","times") else "", s)
    s = s.replace("\\", "\\")
    s = re.sub(r"-?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?", "#", s)
    return re.sub(r"[\s{}$;,.]", "", s)
hits = []
for t, k, D in c.fetchall():
    kn = nums(k)
    if not kn: continue
    for i, d in enumerate(D):
        v = d.get("value_latex") or d.get("value")
        if v is None or str(v).strip() == (k or "").strip(): continue
        if nums(str(v)) == kn and skel(str(v)) == skel(k):
            hits.append((t, i, k, v))
json.dump(hits, open("/audit/numeq_hits.json", "w"), ensure_ascii=False, indent=0)
print(len(hits))
for h in hits: print(h)
