from sympy import *
x = symbols('x', real=True)
g = cos(x) + x/2; print(solveset(diff(g, x) > 0, x, Interval(-7*pi/6, 5*pi/6)), "|", solveset(diff(g, x) < 0, x, Interval(-7*pi/6, 5*pi/6)))
g = cos(x) + x*sqrt(3)/2; print(solveset(diff(g, x) >= 0, x, Interval(pi/3, 7*pi/3)), "|", solveset(diff(g, x) < 0, x, Interval(pi/3, 7*pi/3)))
