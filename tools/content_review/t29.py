from fractions import Fraction as F
import math, sympy as sp
r=math.radians
def chk(name, ineq, key, lo=-30, hi=30, step=F(1,60)):
    bad=[];x=F(lo)
    while x<=hi:
        try: a=ineq(float(x))
        except (ZeroDivisionError,ValueError): a=None
        if a is not None and a!=key(float(x)): bad.append(float(x))
        x+=step
    print('OK ' if not bad else 'BAD',name,bad[:6])
chk('9200',lambda x:(3*x*x+5*x)**5<=32,lambda x:-2<=x<=1/3)
chk('9201',lambda x:(x*x-5*x)**3>216,lambda x:x<-1 or x>6)
chk('9205',lambda x:math.sqrt(x*x-8*x)>3,lambda x:x<-1 or x>9)
chk('9206',lambda x:math.sqrt(x*x-3*x)<2,lambda x:(-1<x<=0) or (3<=x<4))
chk('9207',lambda x:math.sqrt(3*x-2)>x-2,lambda x:2/3<=x<6)
chk('9208',lambda x:math.sqrt(3-x)>1-x,lambda x:-1<x<=3)
print('9202',sp.solve(sp.sqrt(3*sp.Symbol('x')**2-4*sp.Symbol('x')+2)-sp.Symbol('x')-4,sp.Symbol('x')))
x=sp.Symbol('x')
print('9202 roots',[(v,sp.sqrt(3*v*v-4*v+2),v+4) for v in sp.solve(3*x**2-4*x+2-(x+4)**2,x)])
print('9203',[(v,math.sqrt(v+11),1+math.sqrt(v)) for v in (25,)],'9204',math.sqrt(81+19),1+9)
print('9209',sum(v for v in range(-10,10) if v*v+6*v+5<0))
# 9210: ax^2+4x+9a<0 for all x: a<0 and D=16-36a^2<0 -> |a|>2/3 -> a<-2/3
# 9211: ax^2-8x-2<0 all x: a<0 and D=64+8a<0 -> a<-8
# 9213 (0,4)
print('9218',[(v*v/4-3*v/4+0.5) for v in (1,2)], 0.5)
print('9219',[3*x*x+5*x-2 for x in (-3,)])
print('9220 vertex',-1*9+18-11)
for nm,f in (('9221',lambda x:4*x+81/(25*x)),('9222',lambda x:(x+3)*(x+12)/x),('9223',lambda x:(4*x*x-7*x+25)/x),('9224',lambda x:(x**4+x*x+1)/(x*x+1))):
    print(nm,min(f(k/1000) for k in range(1,20000)))
print('9225',max(k/1000*(6-2*k/1000) for k in range(1,3000)))
print('9228',[(11,-1)], math.sqrt(9/4)-math.sqrt(4/9))
print('9229',(3,1),'9230',[(a,b) for a in range(-20,20) for b in range(-20,20) if a-b==3 and a*b==28])
print('9232',sp.solve([x+20*sp.Symbol('y')+10*x*sp.Symbol('y')-40, x+20*sp.Symbol('y')-10*x*sp.Symbol('y')+8],[x,sp.Symbol('y')]))
print('9233',sp.solve([x-sp.Symbol('y')**2+3,x*sp.Symbol('y')**2-54],[x,sp.Symbol('y')]))
y=sp.Symbol('y'); print('9234',sp.solve([x-5*y+20,5/x+5/y-2],[x,y]))
print('9235',153/180,17/20)
print('9236',(math.sin(r(10))*math.sin(r(130))-math.sin(r(100))*math.sin(r(220)))/(math.sin(r(27))*math.cos(r(23))-math.sin(r(157))*math.cos(r(153))))
print('9237',math.cos(r(-225))+math.sin(r(675))+math.tan(r(-1035)),1-math.sqrt(2))
t=math.sqrt(5); print('9238',2*t/(1+t*t),math.sqrt(5)/3)
a=0.6; print('9240',(math.sin(2*a)+math.sin(math.pi-a)*math.cos(a))/math.sin(math.pi/2-a),3*math.sin(a))
t=math.sqrt(7); c2=1/(1+t*t);s2=1-c2; print('9241',4*s2*s2/(5*s2+15*c2))
# 9242: s+c=1/3: sc=(1/9-1)/2=-4/9: s^4+c^4=1-2(sc)^2=1-2*16/81=49/81
print('9242',1-2*(4/9)**2,49/81)
print('9243',math.sin(r(100))*math.cos(r(440))+math.sin(r(800))*math.cos(r(460)))
print('9244',0.65*180)
