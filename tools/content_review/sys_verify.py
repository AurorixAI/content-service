"""Systems of equations: solve the system in the statement with SymPy (reals) and compare with the key.

Statement: one \\begin{cases}/\\begin{array} block whose rows are all equations. Key: ordered pairs/triples
«(a; b)», «(a, b)» or assignments «x = a, y = b» (several solutions separated by «;», «и», «или»).
Pair order: x, y, z first, otherwise alphabetical. Classes: ok, mismatch (missing / extra solution),
nosolution_ok, unparsed, infinite (skipped). Output /audit/sys_verify.json.
"""
import json
import re
import signal
import sys

sys.path.insert(0, "/audit")
import psycopg2
import sympy as sp
import nested_verify2 as nv

_argv = sys.argv; sys.argv = ["x"]
exec(open("/audit/simp_verify.py").read().split("\ndef real_roots")[0].split("import nested_verify2 as nv", 1)[1])  # prep(), wrap_args()
sys.argv = _argv

class _TO(Exception):
    pass


def _alarm(*_):
    raise _TO()


signal.signal(signal.SIGALRM, _alarm)
ORDER = ["x", "y", "z", "t"]


def rows(q):
    m = re.search(r"\\begin\{(cases|array)\}(?:\{[^}]*\})?(.+?)\\end\{\1\}", q, re.S)
    if not m:
        return None
    rs = [r.strip().strip(",;.").strip() for r in re.split(r"\\\\", m.group(2)) if r.strip()]
    rs = [re.sub(r"&", "", r) for r in rs]
    return rs if rs and all(r.count("=") == 1 and not re.search(r"\\(le|ge|leq|geq|ne|neq)\b|[<>]", r) for r in rs) else None


def sym(e):
    return nv.to_sym(prep(e))


def key_solutions(k, varnames):
    k = (k or "").replace("$", " ").replace("\\left", "").replace("\\right", "").replace("\\;", " ").replace("\\,", " ")
    k = re.sub(r"(?<=\d)\{,\}(?=\d)", ".", k)
    if re.search(r"нет решени|нет действительн|∅|\\varnothing|\\emptyset", k):
        return []
    tuples = re.findall(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", k)
    sols = []
    for t in tuples:
        parts = [p.strip() for p in re.split(r";|,(?!\d)", t) if p.strip()]
        if len(parts) == len(varnames):
            sols.append(parts)
    if sols:
        return sols
    # assignment form: x = a, y = b (possibly several groups)
    assigns = re.findall(r"([a-z])\s*=\s*(-?[^,;=]+?)(?=\s*(?:[,;]|\bи\b|\bили\b|$|\s[a-z]\s*=))", k)
    if not assigns:
        return None
    groups, cur = [], {}
    for v, val in assigns:
        if v in cur:
            groups.append(cur); cur = {}
        cur[v] = val.strip()
    groups.append(cur)
    out = []
    for g in groups:
        if set(g) != set(varnames):
            return None
        out.append([g[v] for v in varnames])
    return out


def num(e):
    return complex(sp.N(sym(e), 20))


c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active AND question_latex ~* 'систем'")
res = {"ok": [], "nosolution_ok": [], "mismatch": [], "unparsed": [], "infinite": []}
for tid, q, k in c.fetchall():
    rs = rows(q or "")
    if not rs:
        continue
    try:
        eqs = [sp.Eq(sym(r.split("=")[0]), sym(r.split("=")[1])) for r in rs]
        vs = sorted(set().union(*[e.free_symbols for e in eqs]), key=lambda s: (ORDER.index(s.name) if s.name in ORDER else 9, s.name))
        if not 1 < len(vs) <= 3 or len(vs) > len(eqs):
            res["unparsed"].append([tid, "vars"]); continue
        signal.alarm(10)
        sol = sp.solve(eqs, vs, dict=True)
        signal.alarm(0)
    except Exception as exc:
        signal.alarm(0)
        res["unparsed"].append([tid, type(exc).__name__]); continue
    true = []
    for s_ in sol:
        if len(s_) != len(vs) or any(v.free_symbols for v in s_.values()):
            true = None; break
        vals = [complex(sp.N(s_[v], 20)) for v in vs]
        if all(abs(z.imag) < 1e-9 for z in vals):
            true.append(vals)
    if true is None:
        res["infinite"].append(tid); continue
    ks = key_solutions(k, [v.name for v in vs])
    if ks is None:
        res["unparsed"].append([tid, "key"]); continue
    try:
        kv = [[num(x) for x in s_] for s_ in ks]
    except Exception:
        res["unparsed"].append([tid, "keyval"]); continue
    close = lambda a, b: all(abs(p - q_) < 1e-6 * max(1, abs(p)) for p, q_ in zip(a, b))
    missing = [t for t in true if not any(close(t, u) for u in kv)]
    extra = [u for u in kv if not any(close(t, u) for t in true)]
    if not missing and not extra:
        res["nosolution_ok" if not true else "ok"].append(tid)
    else:
        res["mismatch"].append({"id": tid, "q": q[:300], "key": k, "vars": [v.name for v in vs],
                                "true": [[str(round(z.real, 6)) for z in t] for t in true],
                                "missing": [[str(round(z.real, 6)) for z in t] for t in missing], "extra": [[str(round(z.real, 6)) for z in t] for t in extra]})
json.dump(res, open("/audit/sys_verify.json", "w"), ensure_ascii=False, indent=1)
print({k_: len(v) for k_, v in res.items()})
