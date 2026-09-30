from sympy import *
x = symbols('x', real=True)
ok = lambda n, c: print("OK " if c else "BAD", n)
def sign_ok(fp, segs):  # segs: (lo, hi, sign) — derivative keeps this sign strictly inside
    for lo, hi, s in segs:
        for i in range(1, 400):
            v = lo + (hi - lo)*Rational(i, 400)
            if s*N(fp.subs(x, v)) <= 0: return False
    return True
fp = diff(sin(2*x) - x*sqrt(2), x); ok("39.19(2)", sign_ok(fp, [(-pi/8, pi/8, 1), (pi/8, 7*pi/8, -1)]))
ok("35.22(4)", cos(pi/2) == 0 and cos(0) != 0)
fp = diff(2 + x**2 + 2*x**3 - 2*x**4, x); ok("39.7(6)", sorted(solve(fp, x)) == [-Rational(1, 4), 0, 1] and sign_ok(fp, [(-2, -Rational(1, 4), 1), (-Rational(1, 4), 0, -1), (0, 1, 1), (1, 3, -1)]))
f = 2*sin(2*x) + cos(4*x); vals = [f.subs(x, v) for v in [0, pi/3, pi/12, pi/4]]; ok("40.9(1)", simplify(max(vals, key=N) - Rational(3, 2)) == 0 and simplify(min(vals, key=N) - 1) == 0 and all(0 <= N(f.subs(x, pi/3*Rational(i, 300))) - 1 + 1e-12 and N(f.subs(x, pi/3*Rational(i, 300))) <= 1.5 + 1e-12 for i in range(301)))
F = (x + 1)**2*(x - 2)**2; c = [F.subs(x, v) for v in [-2, 4] + [r for r in solve(diff(F, x), x) if -2 <= r <= 4]]; ok("40.3(3)", (min(c), max(c)) == (0, 100))
fp = diff((x - 2)**2*sqrt(x), x); ok("39.23(2)", sign_ok(fp, [(Rational(1, 1000), Rational(2, 5), 1), (Rational(2, 5), 2, -1), (2, 10, 1)]))
e = 2*tan(x)**2 + 4*cos(x)**2 - 7; ok("30.5(13)", all(simplify(e.subs(x, v)) == 0 for v in [pi/3, -pi/3, 2*pi/3]) and simplify(e.subs(x, pi/4)) != 0)
g = lambda v: N(Abs(sin(v)) - 2*sin(v) - cos(v)); ok("42.55", abs(g(3*pi/4)) < 1e-12 and abs(g(2*pi - atan(Rational(1, 3)))) < 1e-12 and abs(g(7*pi/4)) > 0.1
   and len([i for i in range(1, 20000) if g(2*pi*i/20000)*g(2*pi*(i + 1)/20000) < 0 or g(2*pi*i/20000) == 0]) == 2)
fp = diff(-1/(x - 3)**2, x); ok("39.14(6)", sign_ok(fp, [(3, 20, 1), (-20, 3, -1)]))
f = x - 1 - x**3 - x**2; c = [f.subs(x, v) for v in [-2, 0] + [r for r in solve(diff(f, x), x) if -2 <= r <= 0]]; ok("40.2(2)", (max(c), min(c)) == (1, -2))
