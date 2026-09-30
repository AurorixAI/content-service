import sympy as sp
x,y=sp.symbols('x y'); s=sp.sqrt; R=sp.Rational
def syst(n,eq,ans):
    sol=sp.solve(eq,[x,y],dict=True)
    got=[(sp.simplify(q[x]),sp.simplify(q[y])) for q in sol if sp.im(sp.N(q[x]))==0 and sp.im(sp.N(q[y]))==0]
    ok=len(got)==len(ans) and all(any(abs(sp.N(g[0]-e[0]))<1e-9 and abs(sp.N(g[1]-e[1]))<1e-9 for e in ans) for g in got)
    print('OK ' if ok else 'BAD',n,'' if ok else (got,))
syst('8024',[x**2-4*x*y+3*y**2+2*x-6*y,x**2-x*y+y**2-7],[(3,1),(-3,-1),(1,3)])
syst('8025',[x**2+x*y-2*y**2-x+y,x**2+y**2-8],[(2,2),(-2,-2),((1-2*s(39))/5,(2+s(39))/5),((1+2*s(39))/5,(2-s(39))/5)])
syst('8026',[x**2-3*x*y+14,3*x**2+2*x*y-24],[(2,3),(-2,-3)])
syst('8027',[2*x**2-6*y-x*y,3*x**2-8*y-R(1,2)*x*y],[(0,0),(-1,R(2,5))])
syst('8028',[x**2+3*x*y-10*y**2,x**2-4*x*y+3*y],[(0,0),(R(3,2),R(3,4)),(R(1,3),-R(1,15))])
syst('8029',[x**2+x*y-6*y**2,x**2+3*x*y+2*y-6],[(-9,3),((-1+s(61))/5,(-1+s(61))/10),((-1-s(61))/5,(-1-s(61))/10)])
