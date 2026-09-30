from sympy import *
x, y, u, v, a, b, c = symbols('x y u v a b c')
ok = lambda s, cnd: print("OK " if cnd else "BAD", s)
ok("1251д", Rational(10, 3)*Rational(9, 4) - Rational(1, 2) == 7)
ok("100б", simplify(1/(2*b - 2*a) + 1/(2*b + 2*a) + a**2/(a**2*b - b**3) - 1/b) == 0)
ok("711в", set(solve([3*x + y - 1, 1/x + 1/y + Rational(5, 2)], [x, y])) == {(-Rational(1, 3), 2), (Rational(2, 5), -Rational(1, 5))})
ok("1251з", -Rational(1, 6)*36**2*Rational(1, 6)**3 == -1)
ok("211", ((a - 15*a)**2/(5*a)**2).simplify() == Rational(196, 25))
ok("168а", simplify(((x - a)/(x - b)).subs(x, a*b/(a + b)) - a**2/b**2) == 0)
f = (sqrt(x) - sqrt(2))/(x - 2); ok("504", all(N(f.subs(x, t)) < N(f.subs(x, 0)) for t in [Rational(1, 100), 1, 3, 10, 100]) and simplify(f - 1/(sqrt(x) + sqrt(2))) == 0)
g = (9 + 6*x + x**2)/(x + 3) + sqrt(x); ok("530", (g.subs(x, Rational(36, 100)), g.subs(x, 49)) == (Rational(396, 100), 59))
def yf(t): return 1/t if t < -Rational(1, 2) or t > Rational(1, 2) else 4*t
cnt = lambda val: len([s for s in set(solve(1/x - val, x)) | set(solve(4*x - val, x)) if s.is_real and yf(s) == val])
ok("1250", (cnt(2), cnt(Rational(1, 3)), cnt(0), cnt(-3)) == (1, 2, 1, 0))
ok("179", solve(2*(2*x + 3*(x + 20)) - 240, x) == [12])
ok("1123в", set(solve(c**2 - 5, c)) == {sqrt(5), -sqrt(5)})
ok("909", set(solve(1 - 1/(2 - x) - (6 - x)/(3*x**2 - 12) + 1/(x - 2), x)) == {-3, Rational(2, 3)})
h = (Rational(1, 2)*(a - 1)**2 - 18)*((a + 5)/(a - 7) + (a - 7)/(a + 5)); ok("159", simplify(h - ((a - 1)**2 + 36)) == 0)
ok("706а", set(solve([3*x**2 + 2*y**2 - 11, x + 2*y - 3], [x, y])) == {(-1, 2), (Rational(13, 7), Rational(4, 7))})
ok("740", set(solve((a - 1)*x**2 + 2*a*x + a + 1, x)) == {-1, (a + 1)/(1 - a)} or set(solve((a - 1)*x**2 + 2*a*x + a + 1, x)) == {-1, -(a + 1)/(a - 1)})
ok("204", sorted((k, (k*k - 4*k + 1)//(k - 2)) for k in range(-50, 50) if k != 2 and (k*k - 4*k + 1) % (k - 2) == 0) == [(-1, -2), (1, 2), (3, -2), (5, 2)])
ok("712а", set(solve([y - (x**2 - 8*x + 16), 2*x - 3*y], [x, y])) == {(6, 4), (Rational(8, 3), Rational(16, 9))})
e = (x + 2)**2/(3*x + 9)*(2*x + 6)/(x**2 - 4); ok("126б", (e.subs(x, Rational(1, 2)), e.subs(x, -Rational(3, 2))) == (-Rational(10, 9), -Rational(2, 21)))
ok("532", set(solve(y**2 - 10*y - 24, y)) == {12, -2} and set(solve(y**2 + y - 90, y)) == {9, -10})
ok("82з", simplify(c - (b + c)**2/(2*b) + (b**2 + c**2)/(2*b)) == 0)
ok("98в", simplify(x**2/(x - y)**2 - (x + y)/(2*x - 2*y) - (x**2 + y**2)/(2*(x - y)**2)) == 0)
ok("84", simplify(a + b - (a**2 + b**2)/a - b*(a - b)/a) == 0)
ok("1215б", simplify((a**-3*b**4/9)**-2*(3/(a**-2*b**3))**-3 - 3*b) == 0)
S = {"706.4.2": ([x**2 + y**2 - 100, 3*x - 4*y], {(8, 6), (-8, -6)}), "706.2": ([x - 2*y**2 - 2, 3*x + y - 7], {(Rational(5, 2), -Rational(1, 2)), (Rational(20, 9), Rational(1, 3))}),
  "706.4.3": ([2*x**2 - y**2 - 32, 2*x - y - 8], {(4, 0), (12, 16)}), "711.1": ([x - y - 5, 1/x + 1/y - Rational(1, 6)], {(15, 10), (2, -3)}),
  "711.2": ([x + y - 6, 1/x - 1/y - Rational(1, 4)], {(12, -6), (2, 4)}), "710.2": ([x + 2*y - 4, x**2 + x*y - y + 5], {(-3, Rational(7, 2)), (-2, 3)}),
  "707.4.2": ([x**2 + 4*y - 10, x - 2*y + 5], {(-2, Rational(3, 2)), (0, Rational(5, 2))}), "707.4.3": ([x - 2*y + 1, 5*x*y + y**2 - 16], {(-3, -1), (Rational(21, 11), Rational(16, 11))}),
  "708.1": ([2*x + 4*y - 5*(x - y), x**2 - y**2 - 6], {(-3*sqrt(3)/2, -sqrt(3)/2), (3*sqrt(3)/2, sqrt(3)/2)}), "703.1": ([x - 3 + y, y**2 - x - 39], {(-3, 6), (10, -7)}),
  "702.3": ([x*y + x + 4, x - y - 6], {(1, -5), (4, -2)}), "702.4": ([x + y - 9, y**2 + x - 29], {(4, 5), (13, -4)}), "708.2": ([x - y - 6*(x + y), x**2 - y**2 - 6], {(-Rational(7, 2), Rational(5, 2)), (Rational(7, 2), -Rational(5, 2))})}
for n, (eqs, sol) in S.items(): ok(n, set(solve(eqs, [x, y])) == sol)
