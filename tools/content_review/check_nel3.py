from sympy import *
x = symbols('x', real=True)
ok = lambda s, c: print("OK " if c else "BAD", s)
f = lambda v: real_root(629 - v, 4) + real_root(77 + v, 4) - 8
ok("5.4", f(4) == 0 and f(548) == 0 and all(abs(N(f(Rational(i, 2)))) > 1e-6 for i in range(-154, 1259) if i not in (8, 1096)))
g = lambda v: sqrt(4*v - v**2 - 3)*(sqrt(2)*cos(v) - sqrt(1 + cos(2*v)))
ok("29.3", all(abs(N(g(v))) < 1e-12 for v in [1, 1.2, 1.5, pi/2, 3]) and abs(N(g(2))) > 1e-3 and abs(N(g(2.5))) > 1e-3)
ok("88", [10*a + (a - 1) for a in range(1, 10) if a*(a - 1) == 3*a + 45] == [98])
