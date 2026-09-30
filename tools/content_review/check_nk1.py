from sympy import *
x = symbols('x', real=True)
ok = lambda s, c: print("OK " if c else "BAD", s)
f = lambda v: real_root(v**3 + 5, 5) + real_root(v**4 - 17, 3) - 6
ok("13.29б", f(3) == 0 and all(abs(N(f(Rational(i, 100)))) > 1e-9 for i in range(-1000, 1000) if i != 300))
ok("11.12б", solveset(x**2 - x > 3*x - 1, x, Reals).intersect(solveset(3*x - 1 >= 0, x, Reals)) == Interval.open(2 + sqrt(3), oo))
g = (x**2 - x + 4)/(x**2 + 4); ok("5.84б", g.subs(x, 0) == 1 and g.subs(x, -2) == Rational(5, 4) and all(1 <= g.subs(x, -Rational(i, 10)) <= Rational(5, 4) for i in range(0, 500)))
h = lambda v: cos(2*v)**2/sin(v)**8 + sin(v)**8/cos(2*v)**2 - 2*cos(sqrt(pi**2/4 - v**2))**2; ok("13.23б", simplify(h(pi/2)) == 0 and simplify(h(-pi/2)) == 0)
n = symbols('n', integer=True); ok("5.17", min((k*k - Rational(81, 2)*k + 305) for k in range(1, 100)) == -105 and min((k*k - Rational(61, 2)*k + 205) for k in range(1, 100)) == -Rational(55, 2))
