from sympy import *
x, y, a, b, m = symbols("x y a b m")
ok = []
e = expand((x**2 - 10*x + 6)*(2*x + b)); ok.append(solve(Eq(e.coeff(x, 3), e.coeff(x, 1)), b) == [1])
s = solve([2*x - y - Rational(1, 2), 3*x - 5*y - 12], [x, y]); ok.append(s == {x: Rational(-19, 14), y: Rational(-45, 14)})
ok.append(solve((y - 2)*(y + 2) - (y - Rational(3, 2))**2 - 4, y) == [Rational(41, 12)])
ok.append(set(solve(m**2 - 25, m)) == {5, -5})
ok.append(Rational(3, 16) == Rational(1875, 10000))
ok.append((-Rational(1, 2))**5 == Rational(-1, 32) and (-Rational(1, 2))**6 == Rational(15625, 10**6) and -Rational(24, 10)**2 == Rational(-576, 100))
ok.append(solve(Rational(4, 3)*x + 4 - (Rational(1, 3)*x + 1), x) == [-3])
ok.append(set(solve(25*x**2 - 16, x)) == {Rational(4, 5), -Rational(4, 5)} and [r for r in solve(81*x**2 + 4, x) if r.is_real] == [])
ok.append(expand((-2*a**2*b)**3) == -8*a**6*b**3)
print("checks", len(ok), "all ok:", all(ok), ok)
