import sympy as sp, math
from fractions import Fraction as F
x,y,z=sp.symbols('x y z'); s=sp.sqrt
def val(n,v,e): print('OK ' if abs(float(v)-float(e))<1e-9 else 'BAD',n,float(v),float(e))
val('9066',sp.N(sp.real_root(5*s(2)+7,3)-sp.real_root(5*s(2)-7,3)),2)
val('9067',sp.N(sp.real_root(2+s(5),3)+sp.real_root(2-s(5),3)),1)
print('9069',sp.solve([x**2+y**2-2*z**2,x+y+z-8,x*y+z**2],[x,y,z]))
print('9070',[(a,b,c) for a in range(1,30) for b in range(1,30) for c in range(1,30) if a+b+c==14 and a+b*c==19])
# 9072 check ratio
n=5
num=sum(k*2*k*4*k for k in range(1,n+1)); den=sum(k*3*k*9*k for k in range(1,n+1)); print('9072',(num/den)**(1/3))
n=3;print('9073',[(5+10**(n+1))*sum(10**i for i in range(n+1))+1, (10**(n+1)+2)//3, ((10**(n+1)+2)//3)**2])
print('9074',[m for m in range(1000,10000) if math.isqrt(21*m)**2==21*m][:2])
print('9075',[k for k in range(2,100) if 100<=k**3+k**2<=999 and (k**3+k**2)%5==0],[k**3+k**2 for k in range(2,100) if 100<=k**3+k**2<=999 and (k**3+k**2)%5==0])
print('9077',[(a,b) for a in range(1,60) for b in range(1,a) if a*a-b*b==45])
print('9081',sp.solve(x**3-2*x**2+3*x-18,x))
print('9086',[(a,b) for a in range(-10,11) for b in range(-10,11) if a*a-b*b==3],'9087',[(a,b) for a in range(-10,11) for b in range(-10,11) if a*a-b*b==4])
val('9089',math.sqrt(121*0.04*289),37.4)
val('9090',math.sqrt((36/7)*(25/7)),30/7)
val('9091',(math.sqrt(32)+math.sqrt(8))**2,72)
val('9092',(8*math.sqrt(63)+3*math.sqrt(28)-5*math.sqrt(112))/(2*math.sqrt(7)),5)
val('9093',15*math.sqrt(1.2)+math.sqrt(270)/3-2*math.sqrt(30),2*math.sqrt(30))
val('9094',4/(3-math.sqrt(5))+1/(2-math.sqrt(5))+3*math.sqrt(5)/4,1+3*math.sqrt(5)/4)
print('9096',[v for v in (-8,) if abs(v+6)==v+10])
print('9100',sp.solve(6*x**2+7*x-3,x),'9103',sp.solve([x-y-F(5,2),x**2-y**2-10],[x,y]))
val('9104',64-6,58);val('9105',3*8,24)
d=math.sqrt(64-12); print('9106',8*d)
for v,r in ((5.6409,5.64),(0.9871,0.99),(0.8245,0.82)): print('9107-9',abs(v-r)/v)
print('9085',[sp.solve([x**2+y**2-9,y-x-a0],[x,y]) for a0 in (3*s(2),)])
