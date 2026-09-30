import sympy as sp, itertools, math
from fractions import Fraction as F
x,y,z,a,m,q,n=sp.symbols('x y z a m q n'); s=sp.sqrt; R=sp.Rational
def rr(e,v=x): return sorted({sp.nsimplify(r) for r in sp.solve(e,v) if sp.im(sp.N(r))==0},key=lambda t:float(t))
print('9021',[(x1,x1*R(-1,3)**4) for x1 in sp.solve(x*(1-R(-1,3)**5)/(1+R(1,3))-R(61,3),x)])
print('9022', [k for k in range(1,15) if sum(R(1,2)*R(-1,2)**i for i in range(k))==R(21,64)], R(1,2)*R(-1,2)**5)
# 9023: q=sqrt3, xn=18sqrt3, Sn=26sqrt3+24
for k in range(1,10):
    x1=18*s(3)/s(3)**(k-1); S=x1*(s(3)**k-1)/(s(3)-1)
    if abs(sp.N(S-(26*s(3)+24)))<1e-9: print('9023',sp.simplify(x1),k)
print('9024',[(sp.Rational(3,4)*(5**k-1)-sp.Rational(3,4)*(5**(k-1)-1)) for k in (1,2,3)])
print('9027',(2-3*R(1,4))/(R(-1,8)),'9028',(1-R(4,9))/(3*R(4,9)-R(2,3)))
print('9029',200*.4/500)
print('9032',sp.solve([y+3*x+10,y-x**2+13*x-6],[x,y]),'9033',sp.solve([y+3*x**2-x+3,y+x**2-x+5],[x,y]),'9034',sp.solve([y-4*x**2-3*x-6,y-3*x**2+3*x+3],[x,y]))
print('9037 min',(-10)**2/4*-1-17)
# 9038 g=1/(|x|-x): x<0: 1/(-2x) >0 ok
print('9039 range',[0], 'max at 1:',R(1,2))
print('9040',sp.solve([x**2+(3*a*0)],[x]) if False else '')
aa=sp.symbols('aa')
# sum squares=(3a)^2-2a^2=7a^2=1.75 -> a^2=1/4 a=+-1/2; x^2-1.5x+0.25 -> roots
for av in (R(1,2),-R(1,2)): print('9040 a',av,rr(x**2-3*av*x+av**2))
# 9041: x^2-3.75x+a^3: x1,x2=x1^2
print('9042 roots m-1,m+1 in (-2,4): m>-1 and m<3')
print('9043 biquad')
# x^4+a x^2+a-1=0: t^2+at+a-1=(t+1)(t+a-1)=0 -> t=-1 (no), t=1-a>0 -> a<1 -> two roots ±sqrt(1-a) ; a=1: t=0 one root -> "only two different": a<1
print('9044',sp.solve([(x+y)*(8-x)-10,(x+y)*(y+5)-20],[x,y]))
print('9045',sp.solve([(x**2+y**2)*(x-y)-447,x*y*(x-y)-210],[x,y]))
print('9046',sp.solve([x*y*(x+y)-30,x**3+y**3-35],[x,y]))
print('9047',[ (sp.nsimplify(r[x]),sp.nsimplify(r[y])) for r in sp.solve([x**3+x**3*y**3+y**3-12,x+x*y+y],[x,y],dict=True) if sp.im(sp.N(r[x]))==0 and sp.im(sp.N(r[y]))==0])
print('9048',rr((x+3)**4+(x+5)**4-4)); print('9049',rr((x**2+x)**4-1))
print('9050',sp.solve([sp.real_root(x,3)+sp.real_root(y,3)-3,x*y-8],[x,y]))
print('9052',sp.solve([x+x*y+y-5,y+y*z+z-11,z+z*x+x-7],[x,y,z]))
