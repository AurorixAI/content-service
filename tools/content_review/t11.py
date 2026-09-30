import math, itertools
from fractions import Fraction as F
def chk(name, ineq, key, lo=-30, hi=30, step=F(1,40)):
    bad=[]
    x=F(lo)
    while x<=hi:
        try:
            a=ineq(x)
        except ZeroDivisionError:
            a=None
        except ValueError:
            a=None
        if a is not None:
            b=key(x)
            if a!=b: bad.append(float(x))
        x+=step
    print('OK ' if not bad else 'BAD',name, bad[:5])
r=F
chk('7538',lambda x:(x-2)*(x-5)*(x-12)>0,lambda x:(2<x<5) or x>12)
chk('7539',lambda x:(x+7)*(x+1)*(x-4)<0,lambda x:x<-7 or -1<x<4)
chk('7540',lambda x:(x+48)*(x-37)*(x-42)>0,lambda x:(-48<x<37) or x>42,-60,60)
chk('7541',lambda x:(x+r(7,10))*(x-r(28,10))*(x-r(92,10))<0,lambda x:x<-r(7,10) or r(28,10)<x<r(92,10))
chk('7542',lambda x:(x+9)*(x-2)*(x-15)<0,lambda x:x<-9 or 2<x<15)
chk('7543',lambda x:x*(x-5)*(x+6)>0,lambda x:(-6<x<0) or x>5)
chk('7544',lambda x:(x-1)*(x-4)*(x-8)*(x-16)<0,lambda x:(1<x<4) or (8<x<16))
chk('7545',lambda x:(x+12)*(3-x)>0,lambda x:-12<x<3)
chk('7546',lambda x:-(x+r(1,7))*(x+r(1,3))>=0,lambda x:-r(1,3)<=x<=-r(1,7))
chk('7547',lambda x:(6+x)*(3*x-1)<=0,lambda x:-6<=x<=r(1,3))
chk('7548',lambda x:2*(x-18)*(x-19)>0,lambda x:x<18 or x>19)
chk('7549',lambda x:-4*(x+r(9,10))*(x-r(32,10))<0,lambda x:x<-r(9,10) or x>r(32,10))
chk('7550',lambda x:(8-x)*(x-r(3,10))>=0,lambda x:r(3,10)<=x<=8)
chk('7551',lambda x:(5-x)*(x+8)>=0,lambda x:-8<=x<=5)
chk('7552',lambda x:(x+12)*(x-1)*(x-9)>=0,lambda x:(-12<=x<=1) or x>=9)
chk('7553',lambda x:(2*x+5)*(x-17)>=0,lambda x:x<=-r(5,2) or x>=17)
chk('7554',lambda x:x*(x+9)*(2*x-8)>=0,lambda x:(-9<=x<=0) or x>=4)
chk('7555',lambda x:(x-5)/(x+6)<0,lambda x:-6<x<5)
chk('7556',lambda x:(r(14,10)-x)/(x+r(38,10))<0,lambda x:x<-r(38,10) or x>r(14,10))
chk('7557',lambda x:2*x/(x-r(16,10))>0,lambda x:x<0 or x>r(16,10))
chk('7558',lambda x:(5*x-r(15,10))/(x-4)>0,lambda x:x<r(3,10) or x>4)
chk('7559',lambda x:(5*x+1)/(x-2)>0,lambda x:x<-r(1,5) or x>2)
chk('7560',lambda x:3*x/(2*x+9)<0,lambda x:-r(9,2)<x<0)
chk('7561',lambda x:(x-21)/(x+7)<0,lambda x:-7<x<21)
chk('7562',lambda x:(x+r(47,10))/(x-r(72,10))>0,lambda x:x<-r(47,10) or x>r(72,10))
chk('7563',lambda x:(6*x+1)/(3+x)>0,lambda x:x<-3 or x>-r(1,6))
chk('7564',lambda x:(x+6)/(x-5)<=0,lambda x:-6<=x<5)
chk('7565',lambda x:(2-x)/x>=0,lambda x:0<x<=2)
chk('7566',lambda x:(7*x-2)/(1-x)>=0,lambda x:r(2,7)<=x<1)
chk('7567',lambda x:(1-11*x)/(2*x-3)<=0,lambda x:x<=r(1,11) or x>r(3,2))
chk('7568',lambda x:(x-8)/(x+4)>2,lambda x:-16<x<-4)
chk('7569',lambda x:(3-x)/(x-2)<1,lambda x:x<2 or x>r(5,2))
chk('7570',lambda x:(7*x-1)/x>5,lambda x:x<0 or x>r(1,2))
chk('7571',lambda x:(6-2*x)/(x+4)>3,lambda x:-4<x<-r(6,5))
chk('7572',lambda x:(5*x+4)/x<4,lambda x:-4<x<0)
chk('7573',lambda x:(6*x+1)/(x+1)>1,lambda x:x<-1 or x>0)
chk('7574',lambda x:x/(x-1)>=2,lambda x:1<x<=2)
chk('7575',lambda x:(3*x-1)/(x+2)>=1,lambda x:x<-2 or x>=r(3,2))
import sympy as sp
x=sp.symbols('x')
print(sp.factor(x**4-x**3-51*x**2+49*x+98), [v for v in (1,-1,2,-2,3,-3,4,-4,7,-7) if (x**4-x**3-51*x**2+49*x+98).subs(x,v)==0])
