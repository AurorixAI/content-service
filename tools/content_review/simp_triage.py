# -*- coding: utf-8 -*-
"""Triage of simp_verify mismatches: try known garbling repairs; a repair that makes key and statement numerically equal
proves the defect class. Output simp_triage.json: {id: {"class", "q", "key", "fixed_q"?, "fixed_key"?}}."""
import json, re, sys
sys.path.insert(0, "/audit")
import psycopg2
exec(open("/audit/simp_verify.py").read().split("c = psycopg2.connect")[0])  # prep, key_expr, compare, COND ...

SWALLOW = re.compile(r"([A-Za-z])\^\{(-?\d+)([a-z]+)\}")
def unswallow(s):
    return SWALLOW.sub(lambda m: m.group(1) + "^{" + m.group(2) + "}" + m.group(3), s)
POWFRAC = re.compile(r"\\left\(\s*\\d?frac\{((?:[^{}]|\{[^{}]*\})*)\}\{((?:[^{}]|\{[^{}]*\})*)\}\s*\\right\)\^\{?(\d+)\}?")
def pow_to_den(s):
    return POWFRAC.sub(lambda m: "\\dfrac{" + m.group(1) + "}{(" + m.group(2) + ")^{" + m.group(3) + "}}", s)
def pow_to_num_den(s):  # (A/B)^n written for A/B^n where A carries its own powers: try denominator only
    return s
MIXDIV = re.compile(r"(\d+)\s*:\s*\\d?frac")
def mixed(s):
    return MIXDIV.sub(lambda m: m.group(1) + "\\dfrac", s)

mm = json.load(open("/audit/simp_verify.json"))["mismatch"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
out = {}
for m in mm:
    tid = m["id"]
    c.execute("SELECT question_latex, correct_answer_latex, correct_answer FROM tasks_master WHERE id=%s", (tid,))
    ql, cal, ca = c.fetchone()
    key = cal or ca
    bl = nv.blocks(ql)
    conds, exprs = {}, []
    parts = []
    for b in bl:
        ps = re.split(r"[;,]\s*(?=[a-zA-Z](?:_\{?\d\}?)?\s*=)", b)
        parts += ps if len(ps) > 1 and all(COND.match(x) for x in ps) else [b]
    for b in parts:
        mc = COND.match(b)
        if mc:
            try: conds[nv.to_sym(mc.group(1))] = nv.to_sym(prep(mc.group(2)))
            except Exception: pass
            continue
        if SKIPBLK.search(b): continue
        exprs.append(b)
    exprs = [x for x in exprs if re.search(r"[\d+\-*/^\\]", x)]
    e = exprs[0]
    rec = {"q": e, "key": key, "class": "unexplained"}
    tries = [("key_exponent_swallowed", e, unswallow(key)), ("question_exponent_swallowed", unswallow(e), key),
             ("both_exponent_swallowed", unswallow(e), unswallow(key)), ("key_power_moved_out_of_fraction", e, pow_to_den(key)),
             ("question_mixed_number_as_division", mixed(e), key)]
    for cls, qq, kk in tries:
        if qq == e and kk == key: continue
        k2 = key_expr(kk)
        if k2 is None: continue
        try:
            st, _ = compare(prep(qq), k2, conds)
        except Exception:
            continue
        if st in ("ok", "rounded"):
            rec.update({"class": cls, "fixed_q": qq if qq != e else None, "fixed_key": kk if kk != key else None}); break
    out[tid] = rec
json.dump(out, open("/audit/simp_triage.json", "w"), ensure_ascii=False, indent=1)
import collections
print(collections.Counter(r["class"] for r in out.values()))
