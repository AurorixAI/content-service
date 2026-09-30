from sympy import *
x = symbols('x', real=True)
ok = lambda n, c: print("OK " if c else "BAD", n)
def sign_ok(fp, segs):
    for lo, hi, s in segs:
        for i in range(1, 400):
            v = lo + (hi - lo)*Rational(i, 400)
            if s*N(fp.subs(x, v)) <= 0: return False
    return True
z = lambda e, v: abs(N(e.subs(x, v))) < 1e-10
e = 5*sin(x/6) - cos(x/3) + 3; ok("30.6(5)", z(e, 7*pi) and z(e, -pi) and z(e, 19*pi) and not z(e, 3*pi) and len([i for i in range(-600, 600) if N(e.subs(x, 12*pi*i/600))*N(e.subs(x, 12*pi*(i+1)/600)) <= 0]) <= 4)
ok("39.11(2)", sign_ok(diff((x + 4)**4*(x - 3)**3, x), [(-8, -4, 1), (-4, 0, -1), (0, 3, 1), (3, 6, 1)]))
ok("39.10(2)", sign_ok(diff((x - 1)**3*(x - 2)**2, x), [(-3, 1, 1), (1, Rational(8, 5), 1), (Rational(8, 5), 2, -1), (2, 5, 1)]))
f = -x - 9/x; c = [f.subs(x, v) for v in [-6, -1] + [r for r in solve(diff(f, x), x) if -6 <= r <= -1]]; ok("40.4(4)", (max(c), min(c)) == (10, 6))
f = (x**2 - 4*x)/(x - 2); ok("37.2(6)", expand(f.subs(x, 3) + diff(f, x).subs(x, 3)*(x - 3)) == 5*x - 18)
e = sqrt(3)*tan(x) + 3 - 3/cos(x)**2; ok("30.6(9)", z(e, 0) and z(e, pi/6) and z(e, 7*pi/6) and not z(e, pi/3))
ok("35.23(3)", set(solve(diff(x**-3, x) + Rational(1, 27), x)) == {-3, 3})
ok("27.11", set(solveset(Eq(sin(x - pi/3), S(1)/2), x, Interval(-pi, 3*pi/2))) == {-5*pi/6, pi/2, 7*pi/6})
e = cos(9*x) - 2*sin(3*pi/2 - 3*x); ok("31.7(9)", all(z(e, v) for v in [pi/6, pi/9, -pi/9, pi/9 + pi/3, pi/6 + 2*pi/3]) and not z(e, pi/12)
   and all(any(abs(N((r - c0)/(pi/3)) - round(N((r - c0)/(pi/3)))) < 1e-9 for c0 in [pi/6, pi/9, -pi/9]) for r in solveset(e, x, Interval(0, 2*pi))))
ok("26.10", set(solveset(Eq(cos(x + pi/12), -S(1)/2), x, Interval.open(-pi/6, 4*pi))) == {7*pi/12, 5*pi/4, 31*pi/12, 13*pi/4})
ok("36.19(1)", simplify(diff(x**-9 - 3*x**-3, x) - (9/x**4 - 9/x**10)) == 0)
ok("39.10(3)", sign_ok(diff(x**6/6 + Rational(4, 5)*x**5 + x**4 + 3, x), [(-5, -2, -1), (-2, 0, -1), (0, 5, 1)]))
ok("39.10(1)", sign_ok(diff(x**4/4 - 2*x**3 + 7, x), [(-5, 0, -1), (0, 6, -1), (6, 10, 1)]))
