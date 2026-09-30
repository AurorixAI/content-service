from sympy import *
x=symbols('x')
e=Eq(5/(x**2-4)-8/(x**2-1),2/(x**2-3*x+2)-20/(x**2+3*x+2))
print(solve(e,x))
