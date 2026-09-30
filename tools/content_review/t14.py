from math import *
import random
def ct(x): return 1/tan(x)
def chk(n,f,g,pts=5):
    ok=True
    for _ in range(pts):
        a=random.uniform(0.2,1.3); b=random.uniform(0.2,1.3)
        try:
            if abs(f(a,b)-g(a,b))>1e-9: ok=False
        except ZeroDivisionError: pass
    print('OK ' if ok else 'BAD',n)
def val(n,v,e): print('OK ' if abs(v-e)<1e-9 else 'BAD',n,v,e)
val('7940',cos(-pi)+0-sin(-1.5*pi)+ct(-pi/4),-3)
chk('7941',lambda a,b:tan(-a)*cos(a)+sin(a),lambda a,b:0)
chk('7942',lambda a,b:cos(a)-ct(a)*(-sin(a)),lambda a,b:2*cos(a))
chk('7943',lambda a,b:(cos(-a)+sin(-a))/(cos(a)**2-sin(a)**2),lambda a,b:1/(cos(a)+sin(a)))
chk('7944',lambda a,b:tan(-a)*ct(-a)+cos(-a)**2+sin(a)**2,lambda a,b:2)
chk('7945',lambda a,b:(cos(a)**2-sin(a)**2)/(cos(a)+sin(-a))+tan(-a)*cos(-a),lambda a,b:cos(a))
val('7946',(3-sin(-pi/3)**2-cos(-pi/3)**2)/(2*cos(-pi/4)),sqrt(2))
val('7947',2*sin(-pi/6)-3*ct(-pi/4)+7.5*tan(-pi)+cos(-1.5*pi)/8,2)
chk('7948',lambda a,b:(sin(-a)**3+cos(-a)**3)/(1-sin(-a)*cos(-a)),lambda a,b:cos(a)-sin(a))
chk('7949',lambda a,b:(1-(sin(a)+cos(-a))**2)/(-sin(-a)),lambda a,b:-2*cos(a))
val('7950',cos(radians(135)),-sqrt(2)/2);val('7952',cos(radians(150)),-sqrt(3)/2);val('7953',cos(radians(240)),-.5)
val('7954',cos(radians(19.5))*cos(radians(25.5))-sin(radians(19.5))*sin(radians(25.5)),sqrt(2)/2)
val('7955',cos(7*pi/9+11*pi/9),-1); val('7956',cos(8*pi/7-pi/7),-1)
a=asin(1/sqrt(3)); val('7957',cos(pi/3+a),(sqrt(2)-1)/(2*sqrt(3)))
a=acos(-1/3); val('7958',cos(a-pi/4),(4-sqrt(2))/6)
chk('7959',lambda a,b:cos(3*a)*cos(a)-sin(a)*sin(3*a),lambda a,b:cos(4*a))
chk('7960',lambda a,b:cos(5*a)*cos(2*a)+sin(5*a)*sin(2*a),lambda a,b:cos(3*a))
chk('7961',lambda a,b:cos(pi/7+a)*cos(5*pi/14-a)-sin(pi/7+a)*sin(5*pi/14-a),lambda a,b:0)
chk('7962',lambda a,b:cos(7*pi/5+a)*cos(2*pi/5+a)+sin(7*pi/5+a)*sin(2*pi/5+a),lambda a,b:-1)
chk('7963',lambda a,b:cos(a+b)+cos(pi/2-a)*cos(pi/2-b),lambda a,b:cos(a)*cos(b))
chk('7964',lambda a,b:sin(pi/2-a)*sin(pi/2-b)-cos(a-b),lambda a,b:-sin(a)*sin(b))
val('7965',sin(radians(90)),1);val('7966',sin(radians(60)),sqrt(3)/2)
a=acos(-3/5)+0; a=2*pi-a if False else pi+acos(3/5)  # III quadrant cos=-3/5
val('7969',sin(a+pi/6),(-4*sqrt(3)-3)/10)
a=pi-asin(sqrt(2)/3); val('7970',sin(pi/4-a),-(sqrt(14)+2)/6)
chk('7984',lambda a,b:sin(a+b)+sin(-a)*cos(-b),lambda a,b:cos(a)*sin(b))
chk('7977',lambda a,b:(a-1)/(a+2)-(1-a)/(a*a+3*a+2),lambda a,b:(a-1)/(a+1))
