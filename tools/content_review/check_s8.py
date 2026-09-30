from sympy import *
x = symbols("x")
def six(p):
    r = sorted(solve(p, x), key=lambda z: N(z)); pos = [z for z in r if z > 0]; neg = [z for z in r if z < 0]
    return [simplify(e) for e in (sum(r), prod(r), sum(neg), prod(pos), max(r) - min(r), max(pos) / min(pos))]
print(six(x**4-10*x**2+9), six(x**4-5*x**2+6), six(x**4-19*x**2+90), six(x**4-11*x**2+28))
t = [1, 9]; print("t-roots ±1,±9:", sum([-9,-1,1,9]), 81, -10, 9, 18, 9)
print(Rational(285,10)/5 + Rational(285,10)**2/200, 2*sqrt(Rational(1,2)) > 1)
