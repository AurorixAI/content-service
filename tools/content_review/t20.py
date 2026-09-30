import sympy as sp
x,y=sp.symbols('x y'); R=sp.Rational
for n,eq in (('8316',[9*x**2+9*y**2-13,3*x*y-2]),('8319',[3*x**2-2*y**2-25,x**2-y**2+y-5])):
    print(n,[(sp.nsimplify(s[x]),sp.nsimplify(s[y])) for s in sp.solve(eq,[x,y],dict=True) if sp.im(sp.N(s[x]))==0 and sp.im(sp.N(s[y]))==0])
