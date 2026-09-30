# -*- coding: utf-8 -*-
"""Numeric key-vs-statement check for «упростите / вычислите / найдите значение / преобразуйте / сократите / разложите /
представьте в виде / выполните действия / раскройте скобки» tasks.

The question must contain exactly one expression block (plus optional «x = v» conditions, which are substituted).
The key must be one expression (text answers, lists, ± are skipped). Both are evaluated at several random points
(positive rationals; conditions substituted) and compared. Output: simp_verify.json with ok / mismatch / skipped."""
import json, random, re, sys
sys.path.insert(0, "/audit")
import psycopg2
import sympy as sp
import nested_verify2 as nv

CMD = re.compile(r"^\s*(\d+\)\s*)?(Упростите|Вычислите|Найдите значение|Преобразуйте|Представьте|Сократите|Разложите|Выполните|"
                 r"Раскройте скобки|Приведите подобные|Возведите|Запишите в виде|Вынесите|Вынести|Найдите произведение|Найдите сумму|"
                 r"Найдите разность|Найдите частное|Умножьте|Разделите|Сложите|Вычтите)", re.I)
COND0 = re.compile(r"^\s*([a-zA-Z](?:_\{?\d\}?)?|\\alpha|\\beta|\\varphi)\s*=\s*(.+?)\s*$")
class _C:
    def match(self, b):
        m = COND0.match(b)
        if not m: return None
        rhs = re.sub(r"\\[a-zA-Z]+", "", m.group(2))
        return m if not re.search(r"[a-zA-Zа-яА-Я=<>]", rhs) and re.search(r"\d", rhs) else None
COND = _C()
SKIPBLK = re.compile(r"^\s*[a-zA-Z]\s*(\\ge|\\geq|\\le|\\leq|\\ne|\\neq|>|<|\\in)\s*|^\s*\d+\)\s*$|^\s*[a-z]\s*$")


def prep(e):
    e = re.sub(r"\\mathrm\{\s*(\\[a-z]+)\s*\}", r"\1", e)
    e = e.replace("\\operatorname{tg}", "\\tan ").replace("\\operatorname{ctg}", "\\cot ").replace("\\tg", "\\tan ").replace("\\ctg", "\\cot ")
    e = e.replace("\\operatorname{arctg}", "\\arctan ").replace("\\operatorname{arcctg}", "\\arccot ")
    e = re.sub(r"\\lg\s*", r"\\log_{10} ", e)
    e = e.replace("\\div", ":").replace("\\times", "\\cdot ")
    e = re.sub(r"(\d+(?:\{,\}\d+|[.,]\d+)?)\s*\^\{?\\circ\}?", r"(\1\\cdot\\frac{\\pi}{180})", e)
    e = re.sub(r"\\text\{[^}]*\}", "", e)
    e = e.replace("\\operatorname{\\cot }", "\\cot ").replace("\\operatorname{\\tan }", "\\tan ")
    e = re.sub(r"\\operatorname\{\s*\\(tan|cot)\s*\}", r"\\\1 ", e)
    e = re.sub(r"\\arcctg", r"\\arccot ", e); e = re.sub(r"\\arctg", r"\\arctan ", e)
    e = wrap_args(e)
    return e.strip().rstrip(".;,")


FN = r"\\(?:sin|cos|tan|cot|ln|arcsin|arccos|arctan|arccot|log_\{[^{}]+\}|log_\d)"
ARG = r"-?\d+(?:\.\d+|\{,\}\d+)?\s*(?:\\alpha|\\beta|\\gamma|\\varphi|\\theta|\\pi|[a-zA-Z])?|\\alpha|\\beta|\\gamma|\\varphi|\\theta|[a-zA-Z]"
WRAP = re.compile(r"(" + FN + r")(\s*\^\{[^{}]+\}|\s*\^\d)?\s*(?!\(|\\left|\{|\\(?!alpha|beta|gamma|varphi|theta|pi))(" + ARG + r")(?![\w{])")
def wrap_args(e):
    return WRAP.sub(lambda m: m.group(1) + (m.group(2) or "") + "(" + m.group(3).strip() + ")", e)


def real_roots(x):
    x = x.replace(sp.acot, lambda z: sp.pi / 2 - sp.atan(z))   # Russian convention: arcctg ∈ (0; π)
    return x.replace(lambda z: z.is_Pow and z.exp.is_Rational and z.exp.p == 1 and z.exp.q % 2 == 1 and z.exp.q > 1,
                     lambda z: sp.real_root(z.base, z.exp.q))


def key_expr(k):
    k = (k or "").strip()
    if re.search(r"[А-Яа-яЁё]", k) or "\\pm" in k or ";" in k:
        return None
    bl = nv.blocks(k)
    if len(bl) != 1:
        return None
    e = bl[0]
    if re.search(r"\\(le|ge|leq|geq|ne|neq|in)\b|[<>]", e):
        return None
    if e.count("=") == 1:
        lhs, rhs = e.split("=")
        if re.fullmatch(r"\s*([a-zA-Z]|[a-zA-Z]'|[a-zA-Z]\([a-z]\)|[a-zA-Z]'\([a-z]\)|\([a-z]\s*\\cdot\s*[a-z]\)\([a-z]\))\s*", lhs):
            e = rhs
        else:
            return None
    elif "=" in e:
        return None
    if "," in re.sub(r"\{,\}|\d,\d", "", e):
        return None
    return prep(e)


def fix_syms(x):
    rep = {s: sp.pi for s in x.free_symbols if s.name == "pi"}
    rep.update({s: sp.I for s in x.free_symbols if s.name == "i"})
    return x.subs(rep)


def rounded_ok(a, b, key):
    m = re.search(r"(\d+)(?:\{,\}|[.,])(\d+)\s*\$?\s*$", key or "")
    if not m or abs(a.imag) > 1e-9 or abs(b.imag) > 1e-9:
        return False
    return abs(a.real - b.real) <= 0.5 * 10 ** (-len(m.group(2))) * 1.0001


def evaluate(x, subs):
    v = x.subs(subs)
    return complex(sp.N(v, 30))


def compare(q, k, conds):
    X, Y = real_roots(fix_syms(nv.to_sym(q))), real_roots(fix_syms(nv.to_sym(k)))
    syms = sorted((X.free_symbols | Y.free_symbols) - set(conds), key=str)
    rnd = random.Random(7)
    good = 0
    for _ in range(12):
        vals = dict(conds)
        vals.update({s: sp.Rational(rnd.randint(2, 9), rnd.randint(2, 7)) for s in syms})
        try:
            a, b = evaluate(X, vals), evaluate(Y, vals)
        except Exception:
            continue
        if any(map(lambda z: z != z or abs(z) == float("inf"), (a, b))):
            continue
        if abs(a - b) > 1e-7 * max(1.0, abs(a), abs(b)):
            if not syms and rounded_ok(a, b, k):
                return "rounded", (a, b)
            return "mismatch", (a, b)
        good += 1
        if good >= 5:
            return "ok", None
    return ("ok", None) if good >= 2 else ("undetermined", None)


c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex, correct_answer FROM tasks_master WHERE is_active")
res = {"ok": [], "rounded": [], "mismatch": [], "skip": {}, "undetermined": [], "parse_fail": []}
for tid, ql, cal, ca in c.fetchall():
    q = (ql or "").strip()
    if not CMD.match(q):
        continue
    if re.search(r"(?:^|[\s,(])(при|если)\s+[^$]*$", re.sub(r"\$[^$]*\$", "", q)) and not re.search(r"\$[^$]*=", q):
        res["skip"][tid] = "values given in words"; continue
    bl = nv.blocks(q)
    conds, exprs = {}, []
    parts = []
    for b in bl:
        ps = re.split(r"[;,]\s*(?=[a-zA-Z](?:_\{?\d\}?)?\s*=)", b)
        parts += ps if len(ps) > 1 and all(COND.match(x) for x in ps) else [b]
    for b in parts:
        m = COND.match(b)
        if m:
            try:
                conds[nv.to_sym(m.group(1))] = nv.to_sym(prep(m.group(2)))
            except Exception:
                exprs.append(b)
            continue
        if SKIPBLK.search(b):
            continue
        exprs.append(b)
    exprs = [x for x in exprs if re.search(r"[\d+\-*/^\\]", x)]
    if len(exprs) != 1:
        res["skip"][tid] = f"{len(exprs)} expressions"; continue
    e = exprs[0]
    if re.search(r"(?<![\\a-z])=|\\(le|ge|leq|geq)\b|[<>]|'|\\ldots|\\dots|\\cdots|\\\\|\\begin", e) or re.search(r"^\s*\d+\)", e):
        res["skip"][tid] = "not a single expression"; continue
    k = key_expr(cal or ca)
    if k is None:
        res["skip"][tid] = "key not a single expression"; continue
    try:
        st, info = compare(prep(e), k, conds)
    except Exception as exc:
        res["parse_fail"].append([tid, type(exc).__name__]); continue
    if st == "mismatch":
        res["mismatch"].append({"id": tid, "q": e[:200], "conds": {str(a): str(b) for a, b in conds.items()}, "key": (cal or ca)[:200],
                                "vals": [str(complex(round(info[0].real, 6), round(info[0].imag, 6))), str(complex(round(info[1].real, 6), round(info[1].imag, 6)))]})
    else:
        res[st].append(tid)
json.dump(res, open("/audit/simp_verify2.json", "w"), ensure_ascii=False, indent=1)
print({k: len(v) for k, v in res.items()})
