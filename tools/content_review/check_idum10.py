from sympy import *
x, y, a, b = symbols("x y a b", real=True); ok = []
ok.append(solve([a - b - 1, a**3 - b**3 - 7], [a, b], dict=True) and any(s[a] == 2 and s[b] == 1 for s in solve([a - b - 1, a**3 - b**3 - 7], [a, b], dict=True)))
sols = solve([a + b - 3, a**3 + b**3 - 9], [a, b], dict=True); ok.append({(s[a]**6, s[b]**6) for s in sols} == {(1, 64), (64, 1)})
ok.append(sqrt(64) - sqrt(1) == 7 and sqrt(1) + sqrt(64) == 9)
f = lambda b0, v: log(v) / log(b0); ok.append(f(Rational(1, 5), 20) < f(Rational(1, 5), 15) < f(Rational(1, 5), 10))
for e in [1 - cbrt(x), x**2 + x, 3*x**3 + 2*x**2 + 1]:
    ok.append(simplify(e.subs(x, -x) - e) != 0 and simplify(e.subs(x, -x) + e) != 0)
print("checks", len(ok), "all ok:", all(ok), ok)
