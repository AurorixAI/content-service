import math, statistics as st, sympy as sp
from fractions import Fraction as F
x=sp.Symbol('x')
def rt(e,dom=None):
    return sorted({sp.nsimplify(r) for r in sp.solve(e,x) if sp.im(sp.N(r))==0},key=lambda t:float(t))
def check_eq(name,lhs,rhs,cands):
    good=[]
    for c in cands:
        try:
            if abs(sp.N(lhs.subs(x,c)-rhs.subs(x,c)))<1e-9: good.append(c)
        except: pass
    print(name,good)
s=sp.sqrt
def solve_num(name,f,lo=-30,hi=30):
    out=[];prev=None;xs=[lo+i*0.001 for i in range(int((hi-lo)/0.001)+1)]
    for v in xs:
        try: y=f(v)
        except: y=None
        if y is not None and prev is not None and prev[1]*y<=0: out.append(round((prev[0]+v)/2,3))
        if y is not None: prev=(v,y)
    print(name,sorted(set(out)))
solve_num('9294',lambda x:math.sqrt(x*x-4*x+9)-(2*x-5) if 2*x-5>=0 else 1)
solve_num('9295',lambda x:math.sqrt(x*x+3*x+6)-(3*x+8) if 3*x+8>=0 else 1)
solve_num('9296',lambda x:2*x-1-math.sqrt(x*x+5))
solve_num('9297',lambda x:x+math.sqrt(13-4*x)-4)
solve_num('9298',lambda x:math.sqrt(x+12)-2-math.sqrt(x),0,100)
solve_num('9299',lambda x:math.sqrt(4+x)+math.sqrt(x)-4,0,100)
solve_num('9300',lambda x:math.sqrt(2*x+1)+math.sqrt(3*x+4)-3,-0.5,10)
solve_num('9301',lambda x:math.sqrt(4*x-3)+math.sqrt(5*x+4)-4,0.75,10)
solve_num('9302',lambda x:math.sqrt(x-7)-math.sqrt(x+17)+4,7,200)
solve_num('9303',lambda x:math.sqrt(x+4)-math.sqrt(x-1)-1,1,100)
solve_num('9304',lambda x:math.sqrt(4+math.sqrt(x))-math.sqrt(19-2*math.sqrt(x)),0,100)
solve_num('9305',lambda x:math.sqrt(7+math.sqrt(x))-math.sqrt(11-math.sqrt(x)),0,100)
def chk(name, ineq, key, lo=-30, hi=30, step=0.01):
    bad=[];v=lo
    while v<=hi:
        try: a=ineq(v)
        except (ZeroDivisionError,ValueError): a=None
        if a is not None and a!=key(v): bad.append(round(v,2))
        v+=step
    print('OK ' if not bad else 'BAD',name,bad[:6])
chk('9306',lambda x:math.sqrt(x-2)>3,lambda x:x>11)
chk('9307',lambda x:math.sqrt(x-2)<=1,lambda x:2<=x<=3)
chk('9308',lambda x:math.sqrt(2-x)<x,lambda x:1<x<=2)
chk('9309',lambda x:math.sqrt(5*x+11)>x+3,lambda x:-2<x<1)
for nm,rhs,exp in (('9310',0,'1;1.5'),('9311',1,'0.5;2'),('9312',10,'-1;3.5'),('9313',-1,'none')):
    print(nm,rt(2*x**2-5*x+3-rhs),exp)
print('9317',rt(x*x+x-12),'9318',rt(-x*x+3*x+10),'9319',rt(-8*x*x-2*x+1),'9320',[float(r) for r in rt(7*x*x+4*x-11)])
print('9321 vertex',(-1,-1+2+3),'9322',(-0.5,0.25-0.5+1.25))
print('9326',rt(x**2+3*x+2-(7-x)) , rt(x**2+3*x+2+(7-x)) )
print('9327',rt(3*x*x-6*x+3-(3*x-3)),rt(3*x*x-6*x+3+(3*x-3)))
print('9324',(0,2), 'y(1)=1+p+q=3 -> p=0'); print('9325','q=0; 4+2p=6 -> p=1')
