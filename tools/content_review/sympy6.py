from sympy import *
x,a,b,c=symbols('x a b c',positive=True)
# G10 36.12.5
y=sqrt((2*x+1)/x); k=-1/(2*x**2*sqrt((2*x+1)/x))
print('deriv', simplify(diff(y,x)-k))
# 5/cbrt(4)
print(simplify(5/root(4,3)-5*root(2,3)/2))
# rationalisations
print(simplify(a/(b*sqrt(b))-a*sqrt(b)/b**2), simplify(3/sqrt(b)-3*sqrt(b)/b), simplify(4/sqrt(a+b)-4*sqrt(a+b)/(a+b)), simplify(3/(5*sqrt(c))-3*sqrt(c)/(5*c)), simplify(a/(2*sqrt(3))-a*sqrt(3)/6))
# fraction 9.3
print(simplify(5*b/(15*a*b**4)-2*a**3/(6*a**4*b**3)))
# systems
X,Y=symbols('X Y')
for eqs,ans in [([X-Y,X+Y-4],(2,2)),([X+Y-45,X-Y-13],(29,16)),([4*X+3*Y-14,5*X-Y-8],(2,2)),([5*X-2*Y,3*X+2*Y-16],(2,5)),([X+2*Y-5,X-2*Y-5],(5,0)),([2*X-7*Y+1,X-5*Y+2],(3,1)),([Y-Rational(5,2)*X,Y-8+Rational(3,2)*X],(2,5)),([3*X+4*Y-10,4*X+5*Y-13],(2,1)),([-X+Y-17,X+Y-49],(16,33))]:
    s=solve(eqs,[X,Y]); print(s,ans, s[X]==ans[0] and s[Y]==ans[1])
print(solve([X-Y-4,X**2+Y**2-Rational(17,2)],[X,Y]))
print(solve([Y-Rational(1,2)*X**2+2,Y-X-2],[X,Y]))
# 1169.2
print(Rational(22,10)/Rational(1,4)-Rational(32,10))
print(sin(Rational(1,5)).evalf(8))
