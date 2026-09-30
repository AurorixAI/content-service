from sympy import *
a=symbols('a')
print(simplify((3*a**2-a+3)/(a**3-1)-(a-1)/(a**2+a+1)+2/(1-a)-a/(1-a**3)))
