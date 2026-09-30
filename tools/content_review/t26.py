from fractions import Fraction as F
import itertools
# 9051: fraction n/d, d=n^2-1; (n+2)/(d+2)>1/4 ; (n-3)/(d-3)<1/10
res=[]
for n in range(2,60):
    d=n*n-1
    if d<=0: continue
    if F(n+2,d+2)>F(1,4):
        if d-3!=0 and F(n-3,d-3)<F(1,10) and d-3>0: res.append((n,d))
        elif d-3<0 and F(n-3,d-3)<F(1,10): res.append(('neg',n,d))
print('9051',res)
# 9054: p3=(p1+p2)/2; 48*p3 + 10*p1 =1 ; 48*p3+15*p2=1
import sympy as sp
p1,p2=sp.symbols('p1 p2'); p3=(p1+p2)/2
sol=sp.solve([48*p3+10*p1-1,48*p3+15*p2-1],[p1,p2]); print('9054',sol,[1/sol[p1],1/sol[p2],1/((sol[p1]+sol[p2])/2)])
# 9055: two-digit 10a+b = 2(a^2+b^2)+6 ; 10a+b = 4ab+6
print('9055',[(a,b) for a in range(1,10) for b in range(0,10) if 10*a+b==2*(a*a+b*b)+6 and (a*b>0 and 10*a+b==4*a*b+6 and 6<a*b and 6<a*a+b*b)])
print('9055 loose',[(a,b) for a in range(1,10) for b in range(0,10) if (10*a+b)//(a*a+b*b)==2 and (10*a+b)%(a*a+b*b)==6 and a*b>0 and (10*a+b)//(a*b)==4 and (10*a+b)%(a*b)==6])
# 9057: (n+4)(n-5) in [-18,360]
print('9057',[k for k in range(1,60) if -18<=(k+4)*(k-5)<=360])
# 9061: AP 4 integer terms; largest = sum of squares of other three
r=[]
for a1 in range(-30,31):
    for d in range(-10,11):
        t=[a1+i*d for i in range(4)]
        if d!=0:
            mx=max(t); rest=[v for v in t]; rest.remove(mx)
            if mx==sum(v*v for v in rest): r.append(t)
print('9061',r)
# 9063: three distinct integers geometric, sum -3
r=[]
for a in range(-60,61):
    for q in (F(k,l) for k in range(-12,13) for l in range(1,7)):
        if q in (0,1,-1): continue
        b=a*q;c=a*q*q
        if b.denominator==1 and c.denominator==1 and a+b+c==-3 and len({a,b,c})==3 and a!=0: r.append((a,int(b),int(c)))
print('9063',sorted(set(r)))
# 9064: 1, 1+d, 1+2d ; (1+d+3)^2 = 1*(1+2d)^2 ?? geometric: terms 1, 1+d+3, (1+2d)^2
r=[]
for d in range(-20,21):
    b=1+d+3; c=(1+2*d)**2
    if b*b==1*c: r.append((1,1+d,1+2*d))
print('9064',r)
