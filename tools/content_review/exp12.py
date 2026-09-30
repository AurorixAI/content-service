import json, sympy as sp
x, a, b = sp.symbols("x a b")
T = {11: ("4*x+11", "-5*x**3+2*x**2-4*x+7"), 12: ("9*a**2+a*b-5*b**2", "-2*a-3*b"), 13: ("2*x**3-11*x**2+7*x-3", "4*x+3"),
     14: ("-2*a**2+5*a*b+3*b**2", "3*a-5*b"), 15: ("7*x**2-4*x-5", "-2*x**2+3*x-11"), 16: ("3*a**2+5*a*b-11*b**2", "2*a+7*b"),
     17: ("-3*x+13", "2*x**3-2*x**2+5*x-11"), 18: ("-5*a**2-7*a*b+9*b**2", "a-5*b"), 19: ("-5*x**3-2*x**2+4*x-11", "3*x+2"),
     20: ("a**2-7*a*b+11*b**2", "3*a-7*b")}
gens = lambda e: [x] if e.has(x) else [a, b]
def tex(e):
    g = gens(e); p = sp.Poly(sp.expand(e), *g)
    s = sp.latex(sp.expand(e), order="lex")
    return "$" + s + "$"
out = {}
for n, (f, g) in T.items():
    F, G = sp.sympify(f, locals={"x": x, "a": a, "b": b}), sp.sympify(g, locals={"x": x, "a": a, "b": b})
    key = sp.expand(F * G)
    Ft = sp.Add.make_args(sp.expand(F)); Gt = sp.Add.make_args(sp.expand(G))
    # ordered by degree in the leading-variable sense
    lead = lambda e: sorted(sp.Add.make_args(sp.expand(e)), key=lambda t: tuple(-sp.Poly(t, *gens(e)).degree(v) for v in gens(e)))
    Fl, Gl = lead(F), lead(G)
    e1 = sp.expand(Fl[0] * Gl[0] + Fl[-1] * Gl[-1])                       # only first*first and last*last
    Gs = sp.expand(G - 2 * Gl[-1])                                          # sign of last term of 2nd factor flipped
    e2 = sp.expand(F * Gs)
    e3 = sp.expand(Fl[0] * G + sum(Fl[1:]))                                # multiplied only the first term of the 1st factor
    assert len({key, e1, e2, e3}) == 4, n
    out[n] = dict(q=f"Выполните умножение: ${sp.latex(F, order='lex')}$", F=str(F), G=str(G), key=tex(key), e1=tex(e1), e2=tex(e2), e3=tex(e3))
    print(n, out[n]["key"], "|", out[n]["e1"], "|", out[n]["e2"], "|", out[n]["e3"])
json.dump(out, open("/audit/exp12.json", "w"), ensure_ascii=False, indent=1)
