import math, statistics as st, sympy as sp
from fractions import Fraction as F
def val(n,v,e): print('OK ' if abs(float(v)-float(e))<1e-9 else 'BAD',n,float(v),float(e))
for a in (0.4,0.9):
    val('9245',math.sin(3*a)/math.sin(a)+math.cos(3*a)/math.cos(a),4*math.cos(2*a))
    val('9250',2*math.sin(math.pi/4+2*a)*math.sin(math.pi/4-2*a),math.cos(4*a))
    val('9251',2*math.cos(math.pi/4+2*a)*math.cos(math.pi/4-2*a),math.cos(4*a) if False else 2*math.cos(math.pi/4+2*a)*math.cos(math.pi/4-2*a))
print('9251 sum-to-product: 2cos(A)cos(B)=cos(A+B)+cos(A-B)=cos(pi/2)+cos(4a) ->',math.cos(4*0.4))
x=sp.Symbol('x')
# 9246: roots of 8x^2-6x+1: 1/2, 1/4 ; sin(a+b)=sa cb+ca sb
sa,sb=F(1,2),F(1,4); print('9246',float(sa)*math.sqrt(1-float(sb)**2)+math.sqrt(1-float(sa)**2)*float(sb), math.sqrt(3)*(1+math.sqrt(5))/8)
# 9247: roots of 6x^2-5x+1: 1/2,1/3
ca,cb=0.5,1/3; print('9247',ca*cb-math.sqrt(1-ca**2)*math.sqrt(1-cb**2),(1-2*math.sqrt(6))/6)
val('9248',(-0.75+2.4)/(1+0.75*2.4),33/56)
val('9249',(4/3*-1-1)/(4/3+-1),-7)
print('9254',math.sin(1.57),math.cos(1.58),math.sin(3))
print('9255',math.cos(2),math.cos(math.radians(2)),math.sin(2),math.sin(math.radians(2)))
d=lambda t:math.radians(t)
val('9256',(math.sin(d(136))*math.cos(d(46))-math.sin(d(46))*math.cos(d(224)))/(math.sin(d(110))*math.cos(d(40))-math.sin(d(20))*math.cos(d(50))),2)
val('9257',101*3+101*100/2*-2,-9797); val('9258',26*(20)/2,260)
val('9259',50*(1+ (1+ 49*0.1))/2 ,172.5)
val('9260',-20.7+1.8*12,1.5)  # a13
print('9260 first positive n:',next(n for n in range(1,50) if -20.7+1.8*(n-1)>0))
val('9261',385/7,55); val('9262',2*(3**6-1)/2,728); val('9263',364*(1-F(1,3)),F(728,3))
# 9264
print('9264',(5000*2/50-4*49)/2)
val('9265',300/100,3); val('9266',20*10/2,100); val('9267',math.sqrt(36),6)
val('9271',-81/162+0,0) if False else None
b1=162+81; q=-81/b1; print('9271 b1',b1,'q',q)
b1=67-33; print('9272 q',33/b1)
# 9273: b2+b4=68, b2-b4=60 -> b2=64,b4=4 -> q^2=1/16
print('9273 q^2',4/64)
# 9274: 5,10,15,... total minutes; day when >? need Q
print('9275',[(a1,d) for a1 in range(-20,21) for d in range(-10,11) if 3*a1+3*d==15 and a1*(a1+d)*(a1+2*d)==80])
print('9276',[(a1,d) for a1 in range(-20,21) for d in range(-20,21) if 3*a1+3*d==0 and a1**2+(a1+d)**2+(a1+2*d)**2==50])
# 9277: chimes: each hour h: h strokes; each half-hour: 1 -> 24 half-hours per day: 2*(1+..+12)=156 + 24 = 180
val('9277',2*sum(range(1,13))+24,180)
val('9278',8*4+7,39); val('9279',(701-1)/7+1,101); print('9280 first neg n:',next(n for n in range(1,1000) if 1002-3*(n-1)<0))
print('9281',[n for n in range(1,300) if n*(14+5*(n-1))//2==25450 and n*(14+5*(n-1))%2==0])
print('9283',3/10); print('9284 boys 15/27 -> 16/30',F(15,27)-F(16,30))
print('9285',st.multimode([2,0,1,4,-1,2]),st.median([2,0,1,4,-1,2]))
zs=[-1]*2+[0]+[2]*3+[4]; print('9286',st.pvariance(zs),math.sqrt(st.pvariance(zs)),146/49)
print('9287',st.pvariance([4,5,7,5,9]),st.pvariance([6,9,7,8]))
print('9288',st.pvariance([-2,2,3]),st.pvariance([-3,-1,1,3,4]))
print('9289',sum(x*p for x,p in zip((-3,-2,0,1,3),(.2,.2,.3,.2,.1))))
