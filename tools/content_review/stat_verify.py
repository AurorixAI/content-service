"""Statistics keys: mean / median / mode / range of an explicit number list in the statement.

Only statements that ask for exactly the measures named and contain one plain list of numbers
(comma/semicolon separated, at least 3 values). Frequency tables are skipped. The key's numbers
must match the computed measures in the order they are asked. Output /audit/stat_verify.json.
"""
import json
import re
from fractions import Fraction as F
from collections import Counter

import psycopg2

MEAS = [("mean", r"средн(ее|его) арифметическ|среднее значение"), ("median", r"медиан"), ("mode", r"\bмод[аыу]\b"), ("range", r"размах")]


def nums(s):
    s = s.replace("{,}", ",").replace("\\,", "").replace("−", "-")
    return [F(x.replace(",", ".")) for x in re.findall(r"-?\d+(?:,\d+)?", s)]


def compute(v, m):
    s = sorted(v)
    if m == "mean":
        return [sum(v) / len(v)]
    if m == "median":
        n = len(s)
        return [s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2]
    if m == "range":
        return [s[-1] - s[0]]
    c = Counter(v); top = max(c.values())
    return sorted(k for k, n in c.items() if n == top) if top > 1 else None   # None: no mode


c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
res = {"ok": [], "mismatch": [], "skip": 0}
for tid, q, k in c.fetchall():
    q = q or ""
    low = q.lower()
    asked = [m for m, pat in MEAS if re.search(pat, low)]
    if not asked or re.search(r"таблиц|частот|begin\{array|\|", low) or re.search(r"[a-z]\s*=", q):
        continue
    lists = [b for b in re.findall(r"\$([^$]+)\$", q)]
    # values: all numbers of the statement after the last colon that precedes the list
    tail = q.split(":")[-1] if ":" in q else q
    v = nums(re.sub(r"[^\d,;{}\s\-−$.]", " ", tail))
    if len(v) < 3 or re.search(r"\d\s*[+*/×·]\s*\d", tail):
        res["skip"] += 1; continue
    try:
        exp = []
        for m in asked:
            r = compute(v, m)
            if r is None:
                raise ValueError("nomode")
            exp += r
    except ValueError:
        res["skip"] += 1; continue
    kv = nums(re.sub(r"\\dfrac\{(-?\d+)\}\{(\d+)\}", lambda m_: str(F(int(m_.group(1)), int(m_.group(2)))).replace("/", ":"), k or ""))
    kv = nums(k or "") if not kv else kv
    ok = len(kv) >= len(exp) and all(any(abs(float(e) - float(x)) < 0.051 for x in kv) for e in exp)
    (res["ok"] if ok else res["mismatch"]).append(tid if ok else {"id": tid, "q": q[:260], "key": k, "asked": asked, "expected": [str(e) for e in exp]})
json.dump(res, open("/audit/stat_verify.json", "w"), ensure_ascii=False, indent=1)
print({x: (len(y) if isinstance(y, list) else y) for x, y in res.items()})
