import sympy as sp
x,y=sp.symbols('x y'); R=sp.Rational
def syst(n,eq,ans):
    sol=sp.solve(eq,[x,y],dict=True)
    got={(sp.nsimplify(s[x]),sp.nsimplify(s[y])) for s in sol if sp.im(sp.N(s[x]))==0 and sp.im(sp.N(s[y]))==0}
    exp={(sp.nsimplify(p),sp.nsimplify(q)) for p,q in ans}
    ok=len(got)==len(exp) and all(any(sp.simplify(g[0]-e[0])==0 and sp.simplify(g[1]-e[1])==0 for e in exp) for g in got)
    print('OK ' if ok else 'BAD',n,'' if ok else (got,exp))
syst('7355',[x**3+y**3-28,x*y**2+x**2*y-12],[(1,3),(3,1)])
syst('7356',[x*y**2+x*y**3-10,x+x*y-10],[(5,1)])
syst('7357',[x**3+27*y**3-54,x**2-3*x*y+9*y**2-9],[(3,1)])
syst('7358',[x**2-x*y+y**2-19,x**2+x*y+y**2-49],[(-5,-3),(-3,-5),(3,5),(5,3)])
syst('7359',[x+y-41,sp.sqrt(x/y)+sp.sqrt(y/x)-R(41,20)],[(16,25),(25,16)])
syst('7360',[x+y-10,sp.sqrt(x)+sp.sqrt(y)-4],[(1,9),(9,1)])
def roots(n,e,exp):
    num=sp.numer(sp.together(e)); rs={sp.nsimplify(r) for r in sp.solve(num,x) if sp.im(sp.N(r))==0}
    exp={sp.nsimplify(v) for v in exp}
    ok=len(rs)==len(exp) and all(any(sp.simplify(g-e2)==0 for e2 in exp) for g in rs)
    print('OK ' if ok else 'BAD',n,'' if ok else (rs,exp))
roots('7361',((x+2)/(x-4))**2+16*((x-4)/(x+2))**2-17,{1,R(14,5),6})
roots('7362',((x+1)/(x-3))**2+18*((x-3)/(x+1))**2-11,{2,5,7-4*sp.sqrt(2),7+4*sp.sqrt(2)})
roots('7363',x**2+1/x**2-R(1,2)*(x-1/x)-R(7,2),{2,-R(1,2),1+sp.sqrt(2),1-sp.sqrt(2)})
roots('7364',x**2+1/x**2-R(1,3)*(x+1/x)-8,{R(1,3),3,(-3-sp.sqrt(5))/2,(-3+sp.sqrt(5))/2})
print(sp.factor(12-5*x-2*x**2),sp.factor(15-10*x),sp.factor(3*x**2-36*x-192),sp.factor(x**2-256))
n=sp.symbols('n')
print('7368',sp.solve((n+6)/n+4*n/(n+6)-4,n))
print('7369',sp.solve((n-2)/(n+8)-(n/(n+6)-R(1,6)),n))
print('7370',sp.solve((3*n-7)/(2*(n+3)-11)-(n+3)/n,n))
