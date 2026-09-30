from sympy import *
x = symbols("x", real=True)
def D(vals, m): n = sum(m); mu = Rational(sum(v*k for v, k in zip(vals, m)), n); return Rational(sum(v*v*k for v, k in zip(vals, m)), n) - mu**2
d1, d2 = D([-1,0,2,4],[2,1,3,1]), D([-2,1,4,5],[1,2,3,1]); print(d1, N(d1,3), N(sqrt(d1),3), d2, N(d2,3), N(sqrt(d2),3))
print(D([4,5,7,5,9],[1]*5), D([6,9,7,8],[1]*4), D([-2,2,3],[1]*3), D([-3,-1,1,3,4],[1]*5))
print(Rational(-2+0+3+3+10, 9), 0.1*4+0.5*9+0.3*25+0.1*49-3.9**2)
print([N(e) for e in (cos(163*pi/180)*cos(295*pi/180), sin(170*pi/180)/tan(250*pi/180), cos(314*pi/180)*sin(147*pi/180), tan(200*pi/180)/tan(201*pi/180))])
print([N(e) for e in (sin(2)*cos(2)*sin(1)*sin(pi/180), tan(8*pi/180)/tan(8)/tan(10*pi/180)/tan(sqrt(10)), sin(9*pi/180)*sin(9)*cos(9*pi/180)*cos(9), cos(10*pi/180)*cos(10)*cos(11*pi/180)*cos(sqrt(11)))])
print(expand(Rational(1,4)*(x-1)*(x-2)), solve(-x**2-6*x-11, x), N(cos(pi/3+acos(Rational(1,3)))), N((1-2*sqrt(6))/6))
print([5*n for n in range(1, 12)], ["ср","чт","пт","сб","вс","пн","вт","ср","чт","пт"][9])
