import sympy as sp
x,y,p,t=sp.symbols('x y p t')
print(sp.solve([6*(y-x)-50-y,y-x*y-24],[x,y]))
print(sp.solve([x**2+x*y-3*y-9,3*x+2*y+1],[x,y]))
