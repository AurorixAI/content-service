import sympy as sp
from math import *
a,d,t,v,w,x=sp.symbols('a d t v w x'); R=sp.Rational
print('8075',sp.solve([(a+7)/d**2-R(3,4),a/(d+6)-R(1,2)],[a,d]))
print('8076',sp.solve([a**2+d**2-225,2*(a+d-14)-(2*(a+d))/3],[a,d]))
# 8077: p1 = 1/x, p2=1/(x+5): 5/x+7.5/(x+5)=1
xs=sp.solve(5/x+R(15,2)/(x+5)-1,x); print('8077',xs,[1/(1/q+1/(q+5)) for q in xs])
# 8078: second faster 1.5x: T1=x, T2=x/1.5: 6/x+4/(x/1.5)=1
xs=sp.solve(6/x+4*R(3,2)/x-1,x); print('8078',xs,[q/R(3,2) for q in xs])
# 8079: 270 km, meet after 3h: v1+v2=90; times 270/v1-270/v2=1.35 (one slower)
print('8079',sp.solve([v+w-90,270/v-270/w-R(27,20)],[v,w]))
# 8080: after meeting: one arrives in N after 75min, other M after 48 min; total 90
# let speeds v1 (M->N), v2; meet after t: v1*t = v2*0.8 ; v2*t = v1*1.25 -> t^2=1 -> t=1;
print('8080',sp.solve([v*t-w*R(4,5),w*t-v*R(5,4),(v+w)*t-90],[v,w,t]))
# 8081: tourists: A->B first leaves 6h later; at meeting first walked 12 less than second; after: first reaches B in 8h, second A in 9h
v1,v2,tt=sp.symbols('v1 v2 tt')
# meeting: first walked tt, second tt+6; v1*tt = v2*(tt+6)-12 ; v1*tt=v2*9 ; v2*(tt+6)=v1*8
print('8081',sp.solve([v1*tt-v2*9,v2*(tt+6)-v1*8,v2*(tt+6)-v1*tt-12],[v1,v2,tt]))
