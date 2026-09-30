from sympy import *
x, y, q = symbols('x y q', real=True)
ok = lambda s, c: print("OK " if c else "BAD", s)
ok("155.2", set(solve([x**2 - x*y - y**2 - 19, x - y - 7], [x, y])) == {(17, 10), (4, -3)})
ok("157.1", solve([x - y - 7, x**2 - y**2 - 14], [x, y]) == [(Rational(9, 2), -Rational(5, 2))])
ok("ТЗ5.3", Rational(16, 30) - Rational(15, 27) == -Rational(1, 45))
ok("4.4", [v for v in [-2, 0, 1, sqrt(3)] if simplify(5*v**2 - 4*v - 1) == 0] == [1])
r = set()
for qq in solve(q**2 - 49, q):
    b1 = 14/qq; r.add((b1*qq**4, sum(b1*qq**i for i in range(4))))
ok("407.2", r == {(4802, 800), (-4802, 600)})
ok("413.4", Rational(-1, 27)/(-9) == Rational(1, 243) and 243**Rational(-1, 4) < 1)
s2, c2 = -Rational(5, 13), -Rational(12, 13); ok("548.2", (2*s2*c2, c2**2 - s2**2) == (Rational(120, 169), Rational(119, 169)))
