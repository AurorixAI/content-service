from sympy import *
x, y = symbols('x y', real=True)
ok = lambda n, c: print("OK " if c else "BAD", n)
def sign_ok(fp, segs):
    for lo, hi, s in segs:
        for i in range(1, 400):
            v = lo + (hi - lo)*Rational(i, 400)
            if s*N(fp.subs(x, v)) <= 0: return False
    return True
h = 8*8*sqrt(3)/16; A = 16*y*(1 - y/h); ym = solve(diff(A, y), y)[0]; ok("40.14", simplify(ym - 2*sqrt(3)) == 0 and simplify(16*(1 - ym/h) - 8) == 0)
ok("39.18(2)", sign_ok(diff(cos(2*x) - x*sqrt(3), x), [(-pi/3, -pi/6, 1), (-pi/6, 2*pi/3, -1)]))
f = x**3/3 - x**2 - 3*x + 4; ok("37.15", sorted(f.subs(x, r) for r in solve(diff(f, x), x)) == [-5, Rational(17, 3)])
f = sign(x)*Abs(x)**Rational(1, 3); ok("35.23(2)", all(simplify(diff(cbrt(x), x).subs(x, 27) - Rational(1, 27)) == 0 for _ in [0]) and abs(N(Rational(1, 3)*Abs(-27)**Rational(-2, 3)) - 1/27) < 1e-12)
a = symbols('a', real=True); g = 4*cos(a)**2 - tan(a)*cot(a); vals = [N(g.subs(a, v)) for v in [Rational(i, 1000)*pi/2 for i in range(1, 1000)]]; ok("42.40(2)", -1 < min(vals) and max(vals) < 3 and min(vals) < -0.999 and max(vals) > 2.999)
ok("26.11", solve(-4*a**2 + 4*a - 2 + 1, a) == [Rational(1, 2)])
f = (x**2 + 8)/(x - 1); c = [f.subs(x, v) for v in [-3, 0] + [r for r in solve(diff(f, x), x) if -3 <= r <= 0]]; ok("40.1(4)", (max(c), min(c)) == (-4, -8))
ok("38.4(4)", sign_ok(diff((x**2 + 5*x)/(x - 4), x), [(-6, -2, 1), (-2, 4, -1), (4, 10, -1), (10, 15, 1)]))
ok("39.15(5)", sign_ok(diff(1/(16 - x**2), x), [(-8, -4, -1), (-4, 0, -1), (0, 4, 1), (4, 8, 1)]))
ok("39.22(4)", sign_ok(diff((2*x - 7)/sqrt(3 - x), x), [(-5, Rational(5, 2), 1), (Rational(5, 2), 3, -1)]))
f = sqrt(x**2/2 + 3*x + 5); ok("40.3(2)", f.subs(x, 4) == 5 and f.subs(x, 2) == sqrt(13) and sign_ok(diff(f, x), [(2, 4, 1)]))
ok("10.7(3)", solveset(x**2 - 6*x - 7 > 0, x, S.Reals) == Union(Interval.open(-oo, -1), Interval.open(7, oo)))
ok("38.13(2)", sign_ok(diff(x*sqrt(2)/2 - sin(x), x), [(-pi/4, pi/4, -1), (pi/4, 7*pi/4, 1)]))
e = 1 - cos(x) - tan(x) + sin(x); z = lambda v: abs(N(e.subs(x, v))) < 1e-10
ok("31.7(4)", all(z(v) for v in [0, 2*pi, pi/4, 5*pi/4, -3*pi/4]) and len([i for i in range(0, 4000) if abs(N(cos(2*pi*i/4000))) > 1e-3 and abs(N(e.subs(x, 2*pi*i/4000))) < 1e-9]) == 3)
ok("42.15(3)", solveset((x + 2)*(x - 5)/(x - 3)**2 <= 0, x, S.Reals) == Union(Interval.Ropen(-2, 3), Interval.Lopen(3, 5)))
