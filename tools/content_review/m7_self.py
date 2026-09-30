# Self-consistency of Makarychev 7 keys that had no pair in the book answers: key vs its own statement.
import sys, json, re, random
sys.path.insert(0, "/audit")
import sympy as sp
import nested_verify2 as nv
exec(open("/audit/simp_verify.py").read().split("c = psycopg2.connect")[0].split("import nested_verify2 as nv")[1])
C = json.load(open("/audit/m7_cands.json"))
x = sp.Symbol("x")
def S(s):
    return fix_syms(nv.to_sym(prep(s.replace("$", "").strip().rstrip(".;"))))
def lastmath(q):
    segs = re.findall(r"\$\$?([^$]+)\$\$?", q)
    return segs[-1] if segs else ""
def numkeys(k):
    return [sp.Rational(v.replace(",", ".")) if "." not in v else sp.nsimplify(v.replace(",", ".")) for v in re.findall(r"-?\d+(?:[.,]\d+)?", k.replace("{,}", ","))]
out = []
for c in C:
    for tid, key, q in c["bank"]:
        verdict = "skip"
        try:
            m = lastmath(q)
            if re.search(r"begin\{cases\}", q):
                rows = re.split(r"\\\\", re.sub(r"\\begin\{cases\}|\\end\{cases\}|,\s*$", "", m))
                eqs = []
                for r in rows:
                    r = r.strip().rstrip(",.;")
                    if "=" in r:
                        l, rr = r.split("=", 1); eqs.append(S(l) - S(rr))
                syms = sorted(set().union(*[e.free_symbols for e in eqs]), key=str)
                sol = sp.solve(eqs, syms, dict=True)
                kv = [sp.nsimplify(v) for v in re.findall(r"-?\d+(?:[.,]\d+)?(?:/\d+)?", key.replace("{,}", ",").replace(",", ".").replace("\\dfrac{", "").replace("}{", "/").replace("}", ""))]
                ok = any(sorted(map(sp.nsimplify, s.values()), key=str) == sorted(kv, key=str) or [s[v] for v in syms] == kv for s in sol)
                verdict = "OK" if ok else f"BAD system sol={[{str(k): str(v) for k, v in s.items()} for s in sol]}"
            elif re.search(r"(Решите уравнение|корень уравнения|Найдите корень|Решите)", q) and "=" in m:
                l, r = m.split("=", 1); e = S(l) - S(r)
                v = list(e.free_symbols)
                if len(v) == 1:
                    roots = set(sp.nsimplify(z) for z in sp.solve(e, v[0]) if z.is_real)
                    kn = set(sp.nsimplify(z.replace(",", ".")) for z in re.findall(r"-?\d+(?:[.,]\d+)?", key.replace("{,}", ",").replace("\\dfrac{", "").replace("}{", "/")))
                    kf = key.replace("{,}", ",")
                    kfr = set(sp.Rational(int(a) * (-1 if s else 1), int(b)) for s, a, b in re.findall(r"(-?)\\dfrac\{(\d+)\}\{(\d+)\}", kf))
                    kn = (kn - {sp.nsimplify(p) for p in re.findall(r"\d+", "".join(re.findall(r"\\dfrac\{\d+\}\{\d+\}", kf)))}) | kfr
                    verdict = "OK" if roots == kn or (not roots and re.search(r"нет|∅|empty", key, re.I)) or (roots <= kn and kn - roots <= set()) else f"BAD roots={sorted(map(str, roots))}"
            elif re.search(r"Упростите|многочлен|произведени|Разложите|Возведите|возведение|Выполните|Найдите значение", q) and m and "=" not in m:
                e1, e2 = S(m), S(key.split(";")[0] if ";" in key and ";" not in m else key)
                syms = list(e1.free_symbols | e2.free_symbols); rnd = random.Random(5); good = True
                for _ in range(4):
                    sub = {s: sp.Rational(rnd.randint(2, 13), rnd.randint(2, 5)) for s in syms}
                    a, b = complex(e1.subs(sub)), complex(e2.subs(sub))
                    if abs(a - b) > 1e-9 * max(1, abs(a)): good = False
                verdict = "OK" if good else "BAD expr"
        except Exception as ex:
            verdict = "skip"
        out.append(dict(ex=c["ex"], id=tid, key=key, q=q, v=verdict, book=c["book"]))
json.dump(out, open("/audit/m7_self.json", "w"), ensure_ascii=False, indent=0)
from collections import Counter
print(Counter(o["v"].split()[0] for o in out))
for o in out:
    if o["v"].startswith("BAD"): print(o["id"], "|", o["q"][-110:], "| K:", o["key"][:60], "|", o["v"][:80], "| BOOK:", str(o["book"])[:120])
