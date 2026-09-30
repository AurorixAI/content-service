from sympy import *
x, y = symbols('x y')
E = (1/(x + y) - y**2/(x*y**2 - x**3)) / ((x - y)/(x**2 + x*y) - x/(y**2 + x*y)) - x/(x + y)
print(factor(simplify(E)), simplify(E + (x**2 + y**2)/(x**2 - y**2)))
