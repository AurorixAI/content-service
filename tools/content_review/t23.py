from fractions import Fraction as F
import math
def chk(name, ineq, key, lo=-30, hi=30, step=F(1,60)):
    bad=[];x=F(lo)
    while x<=hi:
        try: a=ineq(x)
        except ZeroDivisionError: a=None
        if a is not None:
            if a!=key(x): bad.append(float(x))
        x+=step
    print('OK ' if not bad else 'BAD',name,bad[:6])
r=F; s6=math.sqrt(6); s15=math.sqrt(15)
chk('8885',lambda x:2*x*x-x<0,lambda x:0<x<r(1,2))
chk('8889',lambda x:x**3-16*x<0,lambda x:x<-4 or 0<x<4)
chk('8890',lambda x:4*x**3-x>0,lambda x:-r(1,2)<x<0 or x>r(1,2))
chk('8891',lambda x:(x*x-1)*(x+3)<0,lambda x:x<-3 or -1<x<1)
chk('8892',lambda x:(x*x-4)*(x-5)>0,lambda x:-2<x<2 or x>5)
chk('8893',lambda x:(x-5)**2*(x*x-25)>0,lambda x:x<-5 or x>5)
chk('8894',lambda x:(x+7)**2*(x*x-49)<0,lambda x:-7<x<7 and x!=-7)
chk('8895',lambda x:(x-3)*(x*x-9)<0,lambda x:x<-3)
chk('8896',lambda x:(x-4)*(x*x-16)>0,lambda x:x>-4 and x!=4)
chk('8899',lambda x:(r(3,2)-x)/(3+x)>=0,lambda x:-3<x<=r(3,2))
chk('8900',lambda x:(r(7,2)+x)/(x-7)<=0,lambda x:-r(7,2)<=x<7)
chk('8901',lambda x:(2*x+1)*(x+2)/(x-3)<0,lambda x:x<-2 or -r(1,2)<x<3)
chk('8902',lambda x:(x-3)*(2*x+4)/(x+1)>=0,lambda x:-2<=x<-1 or x>=3)
chk('8903',lambda x:(x*x+2*x+3)/(x-2)**2<=0,lambda x:False)
chk('8904',lambda x:(x+4)**2/(2*x*x-3*x+1)>=0,lambda x:x<r(1,2) or x>1)
chk('8905',lambda x:(x*x-x)/(x*x-4)>0,lambda x:x<-2 or 0<x<1 or x>2)
chk('8906',lambda x:(9*x*x-4)/(x-2*x*x)<0,lambda x:x<-r(2,3) or 0<x<r(1,2) or x>r(2,3))
chk('8907',lambda x:(x*x-5*x+6)*(x*x-1)>0,lambda x:x<-1 or 1<x<2 or x>3)
chk('8908',lambda x:(x+2)*(x*x+x-12)>0,lambda x:-4<x<-2 or x>3)
chk('8909',lambda x:(x*x-7*x+12)*(x*x-x+2)<=0,lambda x:3<=x<=4)
chk('8910',lambda x:(x*x-3*x-4)*(x*x-2*x-15)<=0,lambda x:-3<=x<=-1 or 4<=x<=5)
chk('8911',lambda x:(x*x-x-12)/(x-1)>0,lambda x:-3<x<1 or x>4)
chk('8912',lambda x:(x*x-4*x-12)/(x-2)<0,lambda x:x<-2 or 2<x<6)
chk('8913',lambda x:(x*x+3*x-10)/(x*x+x-2)<=0,lambda x:-5<=x<-2 or 1<x<=2)
chk('8914',lambda x:(x*x-3*x-4)/(x*x+x-6)>=0,lambda x:x<-3 or -1<=x<2 or x>=4)
chk('8915',lambda x:(x*x+5*x+6)/(x+3)>=0,lambda x:x>=-2 )
chk('8916',lambda x:(x*x-8*x+7)/(x-1)<=0,lambda x:(x<1 or 1<x<=7))
f=lambda x:x/(x-2)+3/x-3/(x-2)>0
def g(x): return float(x)<-s6 or 0<x<2 or float(x)>s6
chk('8917',f,g)
h=lambda x:x*x/(x*x+3*x)+(2-x)/(x+3)-(5-x)/x<0
chk('8918',h,lambda x:-s15<float(x)<-3 or 0<float(x)<s15)
chk('8919',lambda x:(x*x-7*x-8)/(x*x-64)<0,lambda x:-8<x<-1)
chk('8920',lambda x:(x*x+7*x+10)/(x*x-4)>0,lambda x:x<-5 or x>2)
chk('8921',lambda x:(5*x*x-3*x-2)/(1-x*x)>=0,lambda x:-1<x<=-r(2,5))
print('8922',2*3.14159265*2.35)
