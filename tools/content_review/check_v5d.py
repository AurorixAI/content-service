from sympy import *
a, b, m, n, x, y, al = symbols("a b m n x y alpha", positive=True)
I_ = I
cases = {  # key, [old distractor, new1, new2]
 "7.1": (1/a**4, [a**4, 1/a**22, Rational(9,13)]),
 "10_1_4": (sqrt((m+n)**5), [(m+n)**Rational(5,4), ((m+n)**2)**Rational(1,5), sqrt(m**5+n**5)]),
 "3_18_a": (-sin(al)**2, [sin(al)**2, -cos(al)**2, cos(al)**2-cos(al)]),
 "16_18_1": (Rational(1,2)-I_/2, [Rational(1,2)+I_/2, 3+Rational(2,5)*I_, -Rational(13,24)+Rational(13,24)*I_]),
 "10.1": (453000, [453, 4530, 453000000]),
 "9.2": (19, [35, -19, 1]),
 "262_a": ((a+y)/(a-y), [(2*b+1)/(2*b-1), (a-y)/(a+y), (2*b+y)/(2*b-y)]),
 "249.2": (Rational(3,10), [1, Rational(3,20), Rational(6,10)]),
 "10_4_3": ((5*a**5)**Rational(1,6), [5*a**Rational(5,6), (5*a**5)**6, (5*a)**Rational(5,6)]),
 "22_6": (a**2*b*(a**2*b**3)**Rational(1,6), [a**7*b**Rational(9,2), a**2*b**2*(a**2*b**3)**Rational(1,6), a**2*b*(a**2)**Rational(1,6)]),
 "1_4_2": (log(x,5)**2, [log(x**2,5), x**2*log(x,5), 7**(2*x)]),
 "3_7_b": ((sin(al)-cos(al))/(sin(al)+cos(al)), [(sin(al)+cos(al))/(sin(al)-cos(al)), (cos(al)-sin(al))/(sin(al)+cos(al)), -1]),
}
# original expressions (recompute keys from the statement)
orig = {"7.1": a**9/a**13, "10_1_4": (m+n)**Rational(5,2), "3_18_a": 2*cos(al/2)**2*(cos(al)-1), "16_18_1": (3+2*I_)/(1+5*I_), "10.1": 453*1000,
 "9.2": (25-2)*(25**2+25*2+4)-(25-3)*(25**2+25*3+9), "262_a": (2*a*b+2*b*y+a*y+y**2)/(2*a*b-2*b*y+a*y-y**2), "249.2": Rational(13,20)-Rational(7,20),
 "10_4_3": (5*a**5)**Rational(1,6), "22_6": (a**14*b**9)**Rational(1,6), "1_4_2": log(x,5)**2,
 "3_7_b": (cos(pi/2+al)+sin(pi/2-al))/(cos(3*pi/2-al)+cos(pi+al))}
import random
bad = []
for k, (key, ds) in cases.items():
    pts = [{s: Rational(random.randint(11, 29), random.randint(3, 7)) for s in (a, b, m, n, x, y)} | {al: Rational(random.randint(1, 13), 10)} for _ in range(4)]
    val = lambda e, p: complex(N(sympify(e).subs(p)))
    if any(abs(val(key, p) - val(orig[k], p)) > 1e-9 for p in pts): bad.append((k, "KEY"))
    vs = [key] + ds
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            if all(abs(val(vs[i], p) - val(vs[j], p)) < 1e-9 for p in pts): bad.append((k, "EQUAL", i, j))
# 978.7: -3/4 > -4/5 true; distractors false
assert Rational(-3,4) > Rational(-4,5) and not (Rational(3,4) > Rational(4,5))
print("checked", len(cases) + 1, "bad", bad)
