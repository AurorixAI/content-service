from sympy import *
a,b=symbols('a b')
e=2*a*b/(a**2-b**2)+(a-b)/(2*a+2*b)*2*a/(a+b)+b/(b-a)
print(simplify(e))
