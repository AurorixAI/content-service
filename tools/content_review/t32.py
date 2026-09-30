import sympy as sp, math
x,y=sp.symbols('x y'); s=sp.sqrt; R=sp.Rational
def chk(name, cond, key, lo=-30, hi=30, step=0.01):
    bad=[];v=lo
    while v<=hi:
        try: a=cond(v)
        except (ZeroDivisionError,ValueError,OverflowError): a=None
        if a is not None and a!=key(v): bad.append(round(v,2))
        v+=step
    print('OK ' if not bad else 'BAD',name,bad[:6])
def dom(f):
    def g(v):
        try: f(v); return True
        except (ZeroDivisionError,ValueError): return False
    return g
chk('9335',lambda v:6-v-v*v>=0,lambda v:-3<=v<=2)
chk('9336',lambda v:13*v-22-v*v>=0,lambda v:2<=v<=11)
chk('9337',lambda v:(v*v+6*v+5)/(v+7)>=0 if v!=-7 else None,lambda v:(-7<v<=-5) or v>=-1)
chk('9338',lambda v:(v*v-9)/(v*v+8*v+7)>=0 if abs(v*v+8*v+7)>1e-9 else None,lambda v:v<-7 or (-3<=v<-1) or v>=3)
chk('9342',lambda v:v*(v-1)*(v+2)>=0,lambda v:(-2<=v<=0) or v>=1)
chk('9343',lambda v:(v+1)*(2-v)*(v-3)<=0,lambda v:(-1<=v<=2) or v>=3)
print('9339: 1/(x-2)^3 for x<2: derivative -3/(x-2)^4 <0 -> убывает!')
print('9340 cbrt increasing yes; 9341: 1/cbrt(x+1) x<-1: cbrt negative increasing; 1/t for t<0 decreasing in t -> function decreasing in t->... ')
for v1,v2 in ((0,1),(-3,-2)):
    f=lambda t:1/(t-2)**3; print('9339 vals',f(1.0),f(1.5),f(1.9))
g=lambda t:1/math.copysign(abs(t+1)**(1/3),t+1); print('9341 vals',g(-5),g(-3),g(-1.5))
print('9347',[r for r in sp.solve(s(3-x-x**2)-x,x) if sp.im(sp.N(r))==0 and sp.N(r)>=0],'9348',[r for r in sp.solve(s(32-x*x)-x,x)])
print('9351',sp.expand(2*(3*x+1)**2-x*(3*x+1)+3))
print('9352',sp.solve([x+y+1,y**2-7*x-7],[x,y]),'9353',sp.solve([x**2-3*y-13,x-y-3],[x,y]))
print('9357',sp.solve([x**2-y**2-18,x+y-9],[x,y]),'9358',sp.solve([x+y-4,x**2-y**2-32],[x,y]),'9359',sp.solve([x-7-y,x**2-56-y**2],[x,y]),'9360',sp.solve([y-x+5,x**2-10-y**2],[x,y]))
print('9361',sp.solve([y**2+x*y-4,x**2+x*y+3],[x,y]),'9362',sp.solve([x*y+x**2-10,x*y+y**2-15],[x,y]),'9363',sp.solve([x-y-7,x**2+y**2-9+2*x*y],[x,y]),'9364',sp.solve([x+y-8,x**2+y**2-16-2*x*y],[x,y]))
print('9365',sp.solve([x**3-y**3-9,x-y-3],[x,y]),'9366',sp.solve([x**3+y**3-26,x+y-2],[x,y]))
print('9367',sp.solve([(x+2)*(y-3)-1,(x+2)-(y-3)],[x,y]))
print('9368',sp.solve([x/y-y/x-R(5,6),x**2-y**2-5],[x,y]),'9369',sp.solve([x/y-y/x-R(3,2),x**2-y**2-3],[x,y]))
print('9370',sp.solve([1/x+1/y+R(1,6),x-y-5],[x,y]),'9371',sp.solve([1/x-1/y+R(5,4),x+y-3],[x,y]))
print('9372',sp.solve([x-y**2-6,x*y**2-7],[x,y]),'9373',sp.solve([y**2+1-x,x*y**2-12],[x,y]))
print('9375',sp.solve([x-3-y,x**3-y**3-9],[x,y]),'9376',sp.solve([x**3+y**3-2,x*y*(x+y)-2],[x,y]),'9377',sp.solve([x**3+8*y**3-16,2*x*y*(x+2*y)-16],[x,y]))
