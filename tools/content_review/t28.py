import math
from fractions import Fraction as F
def val(n,v,e): print('OK ' if abs(float(v)-float(e))<1e-9 else 'BAD',n,float(v),float(e))
s2=math.sqrt(2);s3=math.sqrt(3)
print('9157',(-25/math.sqrt(5)), -5*math.sqrt(5)); print('9158',-25/(-5*s2), 5*s2, '9159',-25/0.1)
print('9160',math.sqrt(1-0.5),s2/2,'9161',math.sqrt(1+1),'9162',math.sqrt(9))
val('9167',(math.sin(math.pi/4)+0.5-s3)/(s3-0.5-math.cos(math.pi/4)),-1)
val('9168',(s2/2+0.5-1)/(1-0.5-s2/2),(s2-1)/(1-s2))
# 9171-3: sin a=.6 cos a=.8; sin b=-.28, cos b=-.96
ca=.8;sa=.6;sb=-.28;cb=-.96
val('9171',ca*cb+sa*sb,-0.8);val('9172',sa*cb+ca*sb,-0.8);val('9173',ca*cb-sa*sb,-0.6)
a=.7
val('9174',math.sin(2*a)-2*math.sin(a),2*math.sin(a)*(math.cos(a)-1))
val('9175',math.sin(a)+math.sin(a/2),2*math.sin(3*a/4)*math.cos(a/4))
val('9176',math.cos(a)-math.sin(2*a),math.cos(a)*(1-2*math.sin(a)))
val('9177',1-math.sin(2*a)-math.cos(a)**2,math.sin(a)*(math.sin(a)-2*math.cos(a)))
# 9178: cos(a/2)=-8/17, sin(a/2)<0 -> sin(a/2)=-15/17; sin a=2sc=2*(15/17)(8/17)=240/289 (positive!)
sc=-15/17*(-8/17)*2; print('9178 sin a',sc*289,'cos a',(2*(64/289)-1)*289)
# 9179: sin(a/2)=-5/13,cos(a/2)=-12/13: sin a=2*(5/13)(12/13)=120/169; cos a=1-2*25/169=119/169
print('9179',2*(5*12)/169,(1-2*25/169)*169)
val('9180',10+22*6,142);val('9180S',(10+142)*23/2,1748);val('9181',-12,-12);val('9181S',(0-12)*7/2,-42)
val('9182',F(1,3)+17*F(2,3),F(35,3));val('9182S',(F(1,3)+F(35,3))*9,108)
val('9183',(2+120)*10,1220);val('9185',5*(-10)**3,-5000);val('9186',-5000/(-10)**3,5)
val('9187',3*16,48);val('9187S',3*31,93);val('9188',125,125);val('9188S',(5**4-1)/4,156)
val('9189',F(1,4)*63,F(63,4));val('9190',F(1,5)*(1-(-5)**5)/(1+5),F(521,5))
print('9191',(2**2-4*2+3))
x0=(2/3);
print('9194',[(6*x*x+5*x-6) for x in (-1.5,F(2,3))])
