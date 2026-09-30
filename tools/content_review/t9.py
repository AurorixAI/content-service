import sympy as sp
x,y,a,u=sp.symbols('x y a u')
R=sp.Rational
def sol_eq(expr,v,dens=()):
    num=sp.numer(sp.together(expr))
    out=set()
    for r in sp.solve(num,v):
        if sp.im(sp.N(r))!=0: continue
        if any(abs(sp.N(d.subs(v,r)))<1e-12 for d in dens): continue
        out.add(sp.nsimplify(r))
    return out
def chk(n,got,exp):
    exp={sp.nsimplify(e) for e in exp}
    ok=len(got)==len(exp) and all(any(sp.simplify(g-e)==0 for e in exp) for g in got)
    print('OK ' if ok else 'BAD',n,'' if ok else (got,exp))
# fraction-zero
chk('7327',sol_eq((a**3-9*a)/(a**2+a-12),a,(a**2+a-12,)),{0,3})
chk('7328',sol_eq((a**5+2*a**4)/(a**3+a+10),a,(a**3+a+10,)),{0})   # a=-2 makes denominator zero?
chk('7329',sol_eq((a**5-4*a**4+4*a**3)/(a**4-16),a,(a**4-16,)),{0})
chk('7330',sol_eq((5*x**3-15*x**2-2*x+6)/(x**2-9),x,(x**2-9,)),{sp.sqrt(R(2,5)),-sp.sqrt(R(2,5))})
chk('7331',sol_eq((6*x**3+48*x**2-2*x-16)/(x**2-64),x,(x**2-64,)),{sp.sqrt(3)/3,-sp.sqrt(3)/3})
chk('7332',sol_eq((3*x**3-12*x**2-x+4)/(9*x**4-1),x,(9*x**4-1,)),{4})
chk('7333',sol_eq((x**3-4*x**2-6*x+24)/(x**3-6*x),x,(x**3-6*x,)),{4})
chk('7334',sol_eq(2/(x-2)-10/(x+3)-50/(x**2+x-6)+1,x,(x-2,x+3)),{10})
chk('7335',sol_eq((x+5)/(x-1)+(2*x-5)/(x-7)-(30-12*x)/(8*x-x**2-7),x,(x-1,x-7)),{0})
chk('7336',sol_eq((3*x-2)/(x-1)-(2*x+3)/(x+3)-(12*x+4)/(x**2+2*x-3),x,(x-1,x+3)),{-1,7})
chk('7337',sol_eq((5*x-1)/(x+7)-(2*x+2)/(x-3)+63/(x**2+4*x-21),x,(x+7,x-3)),{2,R(26,3)})
chk('7338',sol_eq(x/(x**2+4*x+4)-4/(x**2-4)+16/(x**3+2*x**2-4*x-8),x,(x+2,x-2)),{4})
chk('7339',sol_eq((a+1)/(a-2)+(a-4)/(a+1)-(3*a+3)/(a**2-a-2),a,(a-2,a+1)),{R(3,2)})
chk('7340',sol_eq((3*a-5)/(a**2-1)-(6*a-5)/(a-a**2)-(3*a+2)/(a**2+a),a,(a-1,a+1,a)),{-R(1,2)})
chk('7341',sol_eq(1/(x-7)-1/(x-1)-1/(x-10)+1/(x-9),x,(x-7,x-1,x-10,x-9)),{R(41,5),13})
chk('7342',sol_eq(1/(x+3)-1/(x+9)-1/(x+5)+1/(x+21),x,(x+3,x+9,x+5,x+21)),{-R(33,5),3})
chk('7343',sol_eq(1/(x-4)+1/(x-2)-1/(x+4)-1/(x-5),x,(x-4,x-2,x+4,x-5)),{R(16,5),8})
chk('7344',sol_eq(1/(x+1)+1/(x+3)-1/(x+28)-1/x,x,(x+1,x+3,x+28,x)),{-R(7,4),2})
chk('7347',sol_eq((5*a+7-28*a**2)/(20*a)-a**2,a,(a,)),{-R(7,5),-R(1,2),R(1,2)})
chk('7348',sol_eq((2-18*a**2-a)/(3*a)+3*a**2,a,(a,)),{-R(1,3),R(1,3),2})
chk('7349',sol_eq(12/(x**2+x-10)-6/(x**2+x-6)-5/(x**2+x-11),x,(x**2+x-10,x**2+x-6,x**2+x-11)),{-4,3})
chk('7350',sol_eq(16/(x**2-2*x)-11/(x**2-2*x+3)-9/(x**2-2*x+1),x,(x**2-2*x,x**2-2*x+3,x**2-2*x+1)),{-2,4})
# intersections
chk('7345',sol_eq(x**2+x-9-9/x,x,(x,)),{-3,1,3})
chk('7346',sol_eq(x**2+6*x-4-24/x,x,(x,)),{-6,-4,2})
# systems 7351-7354
for n,eq,ans in [('7351',[x**2-y-7,x**2*y-18],[(-3,2),(3,2)]),('7352',[2*x**2+y-3,x**2*y-1],[(-1,1),(1,1),(-sp.sqrt(2)/2,2),(sp.sqrt(2)/2,2)]),
 ('7353',[x**2-y**2-12,x**2+y**2-20],[(4,2),(4,-2),(-4,2),(-4,-2)]),('7354',[x**2-y**2-21,x**2+y**2-29],[(5,2),(5,-2),(-5,2),(-5,-2)])]:
    sol=sp.solve(eq,[x,y],dict=True)
    got={(sp.nsimplify(s[x]),sp.nsimplify(s[y])) for s in sol if sp.im(sp.N(s[x]))==0 and sp.im(sp.N(s[y]))==0}
    exp={(sp.nsimplify(p),sp.nsimplify(q)) for p,q in ans}
    ok=len(got)==len(exp) and all(any(sp.simplify(g[0]-e[0])==0 and sp.simplify(g[1]-e[1])==0 for e in exp) for g in got)
    print('OK ' if ok else 'BAD',n,'' if ok else (got,exp))
# inequalities/other
print('7324',sp.solve_univariate_inequality(13*(5*x-1)-15*(4*x+2)<0,x),'exp x<8.6')
print('7325',sp.solve_univariate_inequality(6*(7-R(1,5)*x)-5*(8-R(2,5)*x)>0,x),'exp x>-2.5')
print('7315',sp.factor(x**4-47*x**2-98),'7316',sp.factor(x**4-85*x**2+1764),'7322',sp.factor(3*x**2-25*x-28),'7323',sp.factor(2*x**2+13*x-7))
print('7317',sp.solve((x**2-1)*(x**2+1)-4*(x**2-11),x),'7318',sp.solve(x**5+x**4-6*x**3-6*x**2+5*x+5,x),'7319',sp.solve(x**5-x**4-2*x**3+2*x**2-3*x+3,x))
print('7320',sp.solve(x**7-x**6+8*x-8,x),'7321',sp.solve(x**7-x**6-64*x+64,x))
print('7326',sp.solve([1/x+1/(x-11)-R(1,30)],x))
