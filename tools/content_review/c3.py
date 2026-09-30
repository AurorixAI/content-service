from sympy import *
x = symbols('x', real=True)
e = 5*sin(x/6) - cos(x/3) + 3
print([N(e.subs(x, v)) for v in [7*pi, -pi, 19*pi, 3*pi]])
r = [i for i in range(-600, 600) if N(e.subs(x, 12*pi*i/600))*N(e.subs(x, 12*pi*(i+1)/600)) <= 0]; print(r, [N(12*pi*i/600/pi) for i in r])
