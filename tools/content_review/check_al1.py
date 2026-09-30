from sympy import *
x, y = symbols('x y', real=True)
ok = lambda s, c: print("OK " if c else "BAD", s)
ok("347б", simplify(cot(acot(Rational(4, 3)) + acot(-1)) + 7) == 0 or simplify((Rational(4, 3)*(-1) - 1)/(Rational(4, 3) - 1) + 7) == 0)
ok("154.6", set(solve([y - 4*x - 5, y**2 + 2*x + 1], [x, y])) == {(-1, 1), (-Rational(13, 8), -Rational(3, 2))})
ok("182.2", solveset(x - x**2 >= 0, x, Reals).intersect(solveset(-x**2 + 12*x - 35 >= 0, x, Reals)) == EmptySet)
ok("329.4", (sin(5*pi/2), cos(5*pi/2)) == (1, 0))
ok("245.4", tan(-5*pi/4) < 0 and cot(-5*pi/4) < 0)
ok("199.1", set(solve([(x + 2)*(y - 3) - 1, (x + 2) - (y - 3)], [x, y])) == {(-1, 4), (-3, 2)})
