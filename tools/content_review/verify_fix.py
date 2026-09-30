# -*- coding: utf-8 -*-
"""Verify a built restore spec numerically: for every task, the statement as it will be shown (new or current
question_latex) must equal the key as it will be stored (new or current), by simp_verify's comparison.
Usage: verify_fix.py <name>  → prints OK / FAIL per task and exits 1 if any FAIL."""
import json, re, sys
sys.path.insert(0, "/audit")
import psycopg2
exec(open("/audit/simp_verify.py").read().split("c = psycopg2.connect")[0])
spec = json.load(open(f"/audit/restore_J_{sys.argv[1]}.json"))
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
bad = 0
for tid, s in spec.items():
    c.execute("SELECT question_latex, correct_answer_latex, correct_answer FROM tasks_master WHERE id=%s", (tid,))
    ql, cal, ca = c.fetchone()
    q = s["fields"].get("question_latex", ql)
    k = s["fields"].get("correct_answer_latex") or s["fields"].get("correct_answer") or cal or ca
    bl = nv.blocks(q); conds, exprs, parts = {}, [], []
    for b in bl:
        ps = re.split(r"[;,]\s*(?=[a-zA-Z](?:_\{?\d\}?)?\s*=)", b)
        parts += ps if len(ps) > 1 and all(COND.match(x) for x in ps) else [b]
    for b in parts:
        m = COND.match(b)
        if m:
            conds[nv.to_sym(m.group(1))] = nv.to_sym(prep(m.group(2))); continue
        if SKIPBLK.search(b): continue
        exprs.append(b)
    exprs = [x for x in exprs if re.search(r"[\d+\-*/^\\]", x)]
    kk = key_expr(k)
    if len(exprs) != 1 or kk is None:
        print("SKIP", tid, len(exprs), k[:40]); continue
    try:
        st, info = compare(prep(exprs[0]), kk, conds)
    except Exception as exc:
        st, info = "error:" + type(exc).__name__, None
    if st not in ("ok", "rounded"):
        bad += 1; print("FAIL", tid, st, info, "| Q:", exprs[0][:80], "| K:", k[:60])
print("checked", len(spec), "bad", bad)
sys.exit(1 if bad else 0)
