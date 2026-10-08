"""Helpers for authoring + verifying new G11 tasks (batch f1-authoring-2026-10-07).
Every displayed option is rendered from a sympy value computed in the task file,
so the key AND each distractor come from running the described mistake."""
import json, re
from pathlib import Path
import sympy as sp
from sympy import Rational as R, sqrt, S, oo

HERE = Path(__file__).parent
x = sp.Symbol('x', real=True)

def tex(v):
    """sympy number -> LaTeX with \\dfrac, integers plain."""
    v = sp.nsimplify(v) if not isinstance(v, sp.Basic) else v
    s = sp.latex(v, fold_short_frac=False)
    s = re.sub(r'\\frac', r'\\dfrac', s)
    return s

def dec(v):
    """terminating decimal with {,}"""
    v = sp.Rational(v)
    s = sp.N(v, 12)
    t = format(float(s), '.10f').rstrip('0').rstrip('.')
    return t.replace('.', '{,}')

def M(s):            # wrap into $...$
    return f'${s}$'

def pt(a, b):        # coordinates in Russian notation
    return M(rf'\left({tex(a)};\,{tex(b)}\right)')

def interval(a, b, lc=False, rc=False):
    l, r = ('[', ']') if (lc, rc) else ('(', ')')
    l = '[' if lc else '('
    r = ']' if rc else ')'
    f = lambda t: r'-\infty' if t == -oo else (r'+\infty' if t == oo else tex(t))
    return rf'{l}{f(a)};\,{f(b)}{r}'

def union(*ivs):
    return r' \cup '.join(ivs)

ALL = []
def task(skill, diff, q, key, ds, tests=()):
    """key: display string (already $..$). ds: list of (display, explanation). tests: asserts done by caller."""
    nf = lambda t: re.sub(r'\\frac', r'\\dfrac', t).replace('\\ddfrac', '\\dfrac')
    q = nf(q); key = nf(key); ds = [(nf(d), nf(e)) for d, e in ds]
    opts = [key] + [d for d, _ in ds]
    assert len(set(opts)) == len(opts), ('duplicate options', q, opts)
    assert len(ds) >= 2
    for d, e in ds:
        assert e.startswith('Ученик'), e
    ALL.append(dict(skill=skill, diff=diff, q=q, key=key, ds=[list(t) for t in ds]))

def save(skill, start=None):
    start = start or {}
    from collections import Counter
    c = Counter(t['diff'] for t in ALL)
    assert c == Counter({'A': 2, 'B': 3, 'C': 2}), c
    out = []
    n = Counter({d: start.get(d, 1) - 1 for d in 'ABC'})
    for t in ALL:
        n[t['diff']] += 1
        out.append(dict(id=f"GEN_{skill}_{t['diff']}_{n[t['diff']]:02d}", **t))
    (HERE / f'{skill}.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(skill, 'OK', len(out), 'tasks; all sympy asserts passed')

from sympy import Interval, Union, FiniteSet
from sympy.calculus.util import continuous_domain

def settex(st):
    """Render a sympy set of reals as $..$ using ; separators (Russian style)."""
    st = sp.Union(st) if not isinstance(st, sp.Set) else st
    parts = list(st.args) if isinstance(st, sp.Union) else [st]
    out = []
    def f(t): return r'-\infty' if t == -oo else (r'+\infty' if t == oo else tex(t))
    for p in sorted(parts, key=lambda q: float(q.inf if q.is_Interval else q.args[0])):
        if p.is_Interval:
            out.append(('[' if (not p.left_open) else '(') + f(p.start) + r';\,' + f(p.end) + (']' if (not p.right_open) else ')'))
        else:
            out.append('{' + r';\,'.join(f(a) for a in sorted(p.args)) + '}' if False else r'\{' + r';\,'.join(f(a) for a in sorted(p.args)) + r'\}')
    return M(r' \cup '.join(out))

def excl(*pts):
    return sp.S.Reals - FiniteSet(*pts)

def nroots_scan(expr, lo=-12.0, hi=12.0, n=24001):
    """count transversal real roots of expr(x)=0 numerically: sign change confirmed by bisection (poles rejected)."""
    import math
    fn = sp.lambdify(x, expr, 'math')
    def f(t):
        try:
            v = fn(t)
            return v if isinstance(v, float) or isinstance(v, int) else float(v)
        except Exception:
            return float('nan')
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    ys = [f(t) for t in xs]
    cnt = 0
    for i in range(n - 1):
        a, b = ys[i], ys[i + 1]
        if math.isnan(a) or math.isnan(b): continue
        if a == 0:
            cnt += 1; continue
        if a * b < 0:
            l, r = xs[i], xs[i + 1]; fl = a
            for _ in range(80):
                m = (l + r) / 2; fm = f(m)
                if math.isnan(fm): break
                if fl * fm <= 0: r = m
                else: l, fl = m, fm
            if abs(f((l + r) / 2)) < 1e-6: cnt += 1
    return cnt
