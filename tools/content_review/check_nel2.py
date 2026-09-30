from sympy import *
x, y, t, n = symbols('x y t n', positive=True)
ok = lambda s, c: print("OK " if c else "BAD", s)
e = lambda v: 4**v + 4**(-v) + 2**v - 2**(-v) - 4
ok("20:2", abs(N(e(log((1 + sqrt(5))/2, 2)))) < 1e-12 and abs(N(e(log(sqrt(2) - 1, 2)))) < 1e-12 and e(0) != 0)
L = lambda a, b: log(a)/log(b)
ok("17.1:8.4", all(abs(N(L(p, q) - L(q, p) - Rational(8, 3))) < 1e-12 and p*q == 16 for p, q in [(8, 2), (Rational(1, 4), 64)]) and abs(N(L(2, 8) - L(8, 2) - Rational(8, 3))) > 1)
s = log(3, 3)*0 + log(4, 3); ok("17.1:5.4", abs(N(log(2*(4*3**s - 6), 2) - log(9**s - 6, 2) - 1)) < 1e-12)
ok("21.1.1:3", 12*11*9 + 9*12*8 == 2052)
ok("21.1.3:24", solve(x*(x + 1) - 90, x) == [9] and solve((x + 2)*(x + 1) - 132, x) == [10])
ok("21.2:6.1", solve(Rational(2, 3)*(n - 2) - 2, n) == [5])
k = symbols('k'); ok("21.2:5.5", solve(-Rational(2, 3)*(17 - k) + Rational(3, 4)*k, k) == [8] and binomial(17, 8) == 24310)
ok("22.6:1", Rational(8, 10)**2 == Rational(64, 100))
