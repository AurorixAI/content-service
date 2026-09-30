# -*- coding: utf-8 -*-
"""Three-way check for every candidate (numeric mismatches + book mismatches/differences):
statement expression (as in simp_verify), bank key, textbook answer. Verdicts:
* key_wrong_book_confirms: statement == book answer, statement != key  → key can be replaced by the book answer;
* key_ok_book_noise: statement == key (book text differs — OCR / other item);
* both_differ: statement != key and != book (statement garbled, or book item mapped wrongly) → manual;
* no_book / unparsed → manual. Output cross_check.json."""
import json, re, sys, subprocess
sys.path.insert(0, "/audit")
import psycopg2
exec(open("/audit/simp_verify.py").read().split("c = psycopg2.connect")[0])
import importlib.util

def load_answers(book):
    src = open("/audit/tb_answers.py").read().split("db = psycopg2.connect")[0]
    g = {"__name__": "tba", "sys": sys}
    old = sys.argv; sys.argv = ["x", book]
    exec(src, g); sys.argv = old
    return g["ANS"], g["locate"], g["BOOKS"][book][0]

BOOKS = ["merzlyak10", "nikolsky11", "vilenkin6", "makarychev9", "alimov9"]
ans = {b: load_answers(b) for b in BOOKS}
by_tb = {v[2]: b for b, v in ans.items()}

cands = set(json.load(open("/audit/unexpl_ids.json")))
for b in BOOKS:
    r = json.load(open(f"/audit/tba_{b}.json"))
    cands |= {x["id"] for x in r["mismatch"]} | {x["id"] for x in r["differ"]}

def q_expr(ql):
    bl = nv.blocks(ql); conds, exprs, parts = {}, [], []
    for b in bl:
        ps = re.split(r"[;,]\s*(?=[a-zA-Z](?:_\{?\d\}?)?\s*=)", b)
        parts += ps if len(ps) > 1 and all(COND.match(x) for x in ps) else [b]
    for b in parts:
        m = COND.match(b)
        if m:
            try: conds[nv.to_sym(m.group(1))] = nv.to_sym(prep(m.group(2)))
            except Exception: pass
            continue
        if SKIPBLK.search(b): continue
        exprs.append(b)
    exprs = [x for x in exprs if re.search(r"[\d+\-*/^\\]", x)]
    return (exprs[0], conds) if len(exprs) == 1 else (None, conds)

def as_key(s):
    s = (s or "").strip()
    return key_expr(s if "$" in s else "$" + s + "$")

c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
out = {}
for tid in sorted(cands):
    c.execute("SELECT source_reference, question_latex, correct_answer_latex, correct_answer FROM tasks_master WHERE id=%s AND is_active", (tid,))
    row = c.fetchone()
    if not row: continue
    src, ql, cal, ca = row
    key = cal or ca
    tb = (src or "").split("::")[0]
    book_txt = None
    if tb in by_tb:
        A, locate, _ = ans[by_tb[tb]]
        ex, it = locate(tid, src)
        a = A.get(ex or "")
        if a:
            book_txt = a.get(it) if it else (a.get("") or (list(a.values())[0] if len(a) == 1 else None))
    rec = {"src": src, "q": ql[:300], "key": key, "book": book_txt}
    e, conds = q_expr(ql)
    kk = key_expr(key)
    bk = as_key(book_txt) if book_txt else None
    vk = vb = None
    if e and CMD.match(ql.strip()):
        try:
            if kk: vk = compare(prep(e), kk, conds)[0]
        except Exception: vk = "err"
        try:
            if bk: vb = compare(prep(e), bk, conds)[0]
        except Exception: vb = "err"
    ok = ("ok", "rounded")
    if vb in ok and vk == "mismatch": v = "key_wrong_book_confirms"
    elif vk in ok: v = "key_ok"
    elif vk == "mismatch" and vb == "mismatch": v = "both_differ"
    elif book_txt is None: v = "no_book" if vk == "mismatch" else "manual"
    else: v = "manual"
    rec.update({"verdict": v, "q_vs_key": vk, "q_vs_book": vb})
    out[tid] = rec
json.dump(out, open("/audit/cross_check.json", "w"), ensure_ascii=False, indent=1)
import collections
print(len(out), collections.Counter(r["verdict"] for r in out.values()))
