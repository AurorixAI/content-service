"""Number theory keys: НОД / НОК of listed numbers, prime factorisation, list of all divisors.

Only statements with one clear request and plain integers. Output /audit/nt_verify.json.
"""
import json
import math
import re
from functools import reduce

import psycopg2
import sympy as sp


def ints(s):
    s = re.sub(r"(?<=\d)\s(?=\d{3}\b)", "", s.replace("\\,", "").replace("\\ ", " "))
    return [int(x) for x in re.findall(r"\d+", s)]


def expr_value(k):
    """Evaluate a factorisation key like 2^{3} \\cdot 3 \\cdot 5^{2}."""
    k = k.replace("$", "").replace("\\cdot", "*").replace("\\times", "*").replace("·", "*").replace("{", "(").replace("}", ")").replace("^", "**")
    k = k.split("=")[-1]
    if not re.fullmatch(r"[\d\s*()]+", k):
        return None, None
    v = eval(k)
    bases = [int(b) for b in re.findall(r"(\d+)\s*(?:\*\*|\*|$|\))", k)]
    return v, bases


c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active")
res = {"ok": [], "mismatch": [], "skip": 0}
for tid, q, k in c.fetchall():
    q, k = q or "", k or ""
    low = q.lower()
    kind = None
    if re.search(r"наибольш\w* общ\w* делител|\bнод\b|\\text\{нод\}", low) and not re.search(r"нок|кратн", low):
        kind = "gcd"
    elif re.search(r"наименьш\w* общ\w* кратн|\bнок\b|\\text\{нок\}", low) and not re.search(r"нод|делител", low):
        kind = "lcm"
    elif re.search(r"разложите на простые множители", low):
        kind = "fact"
    elif re.search(r"(запишите|выпишите|найдите) все делители", low):
        kind = "divs"
    if not kind or re.search(r"[a-z]\s*[=^]|\\cdot|\^|таблиц|если|при каких|задач|сколько|докаж", q) or len(re.findall(r"\$", q)) > 8:
        continue
    nums = ints(" ".join(re.findall(r"\$([^$]+)\$", q)) or q.split(":")[-1])
    if kind in ("gcd", "lcm") and not 2 <= len(nums) <= 4:
        res["skip"] += 1; continue
    if kind in ("fact", "divs") and len(nums) != 1:
        res["skip"] += 1; continue
    try:
        if kind == "gcd":
            exp, got = reduce(math.gcd, nums), ints(k.split("=")[-1])
            ok = got[-1:] == [exp]
        elif kind == "lcm":
            exp, got = reduce(lambda a, b: a * b // math.gcd(a, b), nums), ints(k.split("=")[-1])
            ok = got[-1:] == [exp]
        elif kind == "fact":
            v, bases = expr_value(k)
            if v is None:
                res["skip"] += 1; continue
            exp, got = nums[0], v
            ok = v == nums[0] and all(sp.isprime(b) for b in bases)
        else:
            exp, got = sp.divisors(nums[0]), sorted(set(ints(k)))
            ok = got == exp
    except Exception:
        res["skip"] += 1; continue
    (res["ok"] if ok else res["mismatch"]).append(tid if ok else {"id": tid, "kind": kind, "q": q[:220], "key": k[:160], "expected": str(exp)[:120], "got": str(got)[:120]})
json.dump(res, open("/audit/nt_verify.json", "w"), ensure_ascii=False, indent=1)
print({x: (len(y) if isinstance(y, list) else y) for x, y in res.items()})
