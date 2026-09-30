from math import *
def val(n,v,e): print('OK ' if abs(v-e)<1e-9 else 'BAD',n,v,e)
val('8086',2*((0.25-1)/2),-3/4) if False else None
# sin2a = (s+c)^2-1
val('8086',0.25-1,-3/4); val('8087',1-(1/3)**2,8/9) ; val('8088',1-(1/4)**2,15/16)
val('8089',cos(radians(30)),sqrt(3)/2);val('8090',cos(radians(45)),sqrt(2)/2);val('8091',cos(pi/4),sqrt(2)/2);val('8092',cos(pi/6),sqrt(3)/2)
t=0.6; val('8103',2*t/(1-t*t),15/8)
val('8104',tan(pi/4),1); val('8105',3*tan(radians(30)),sqrt(3)); val('8106',2*tan(radians(150)),-2/sqrt(3))
val('8107',cos(radians(2025)),-sqrt(2)/2);val('8108',tan(radians(570)),sqrt(3)/3);val('8109',1/tan(radians(960)),sqrt(3)/3);val('8110',tan(11*pi/6),-sqrt(3)/3)
val('8111',cos(radians(150)),-sqrt(3)/2);val('8112',sin(radians(315)),-sqrt(2)/2);val('8113',tan(-2*pi/3),sqrt(3))
ct=lambda x:1/tan(x)
val('8114',cos(radians(630))-sin(radians(1470))-ct(radians(1125)),-1)
val('8115',tan(radians(1800))-sin(radians(495))+cos(radians(945)),-sqrt(2))
val('8116',sin(-7*pi)-2*cos(13*pi/3)-tan(7*pi/4),0)
val('8117',cos(-9*pi)+2*sin(-49*pi/6)-ct(-21*pi/4),-1)
a=0.7
val('8118',cos(pi-a)**2+sin(a-pi)**2,1)
val('8119',cos(pi-a)*cos(3*pi-a)-sin(a-pi)*sin(a-3*pi),cos(2*a))
