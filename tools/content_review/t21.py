from fractions import Fraction as F
def val(n,v,e): print('OK ' if abs(float(v)-float(e))<1e-9 else 'BAD',n,float(v),float(e))
def S(b1,q,n): return b1*n if q==1 else b1*(1-q**n)/(1-q)
# 8435: b6=96,b8=384: q^2=4
for q in (2,-2):
    b1=F(96)/q**5; print('8435 q',q,'b1',b1, 'key form check', (3 if q==2 else -3))
# 8436-8439 formulas
for n in (3,5):
    val('8436',sum(F(1,5)*5**k for k in range(1,n+1)),(5**n-1)/4)
    val('8437',sum(3*2**(k-1) for k in range(1,n+1)),3*(2**n-1))
    val('8438',sum(3**(1+k) for k in range(1,n+1)),9*(3**n-1)/2)
    val('8439',sum(2**(k+2) for k in range(1,n+1)),8*(2**n-1))
    val('8440',sum(3**(k-1) for k in range(1,n+1)),(3**n-1)/2)
    val('8442',sum(2**k for k in range(1,n+1)),2*(2**n-1))
    val('8444',sum(F(1,2)*F(-1,2)**(k-1) for k in range(1,n+1)),(1-F(-1,2)**n)/3)
    x=F(3,2)
    val('8441',sum((-x)**(k-1) for k in range(1,n+1)),(1-(-x)**n)/(1+x))
    val('8443',sum(x**(2*(k-1)) for k in range(1,n+1)),(1-x**(2*n))/(1-x**2))
    val('8445',sum((-x**3)**(k-1) for k in range(1,n+1)),(1-(-x**3)**n)/(1+x**3))
# 8446: b7=72.9,q=1.5 -> b1=72.9/1.5^6
b1=F(729,10)/F(3,2)**6; val('8446',S(b1,F(3,2),7),205.9)
b1=F(16,9)/F(2,3)**4; val('8447',S(b1,F(2,3),7),F(2059,81))
b1=F(10,9)/F(1,3)**4; val('8448',S(b1,F(1,3),5),F(1210,9))
# 8449: b1=2,b5=162: q^4=81 q=+-3, even terms negative -> q=-3
val('8449',S(2,-3,6),-364)
# 8450: b1+b2=8, b3+b4=72 -> q^2=9, q=3, b1=2 ; question truncated
print('8450 b1=2,q=3', [2*3**k for k in range(6)])
val('8451',F(12,1000)/F(1,5)**7,937.5)
n=4
val('8452',F(2**(n+2)-2**(n-2),2**n),F(15,4)); val('8453',F(25**n-5**(2*n-1),5**(2*n)),F(4,5))
val('8463',S(F(1,2),2,6),31.5); val('8464',S(-2,F(1,2),5),F(-31,8)); val('8465',S(1,F(-1,3),4),F(20,27)); val('8466',S(-5,F(-2,3),5),F(-275,81))
b1=F(635)/ (2**7-1); val('8467',b1,5); val('8467b',b1*64,320)
b1=F(85)*(1+2)/(1-(-2)**8); val('8468',b1,-1); val('8468b',b1*(-2)**7,128)
for nn in range(1,12):
    if S(3,2,nn)==189: print('8469 n',nn)
    if S(5,2,nn)==635: print('8470 n',nn)
    if S(256,F(-1,2),nn)==170: print('8471 n',nn)
    if S(-9,-2,nn)==-99: print('8472 n',nn)
    if S(7,3,nn)==847: print('8473 n',nn,7*3**(nn-1))
    if S(8,2,nn)==4088: print('8474 n',nn,8*2**(nn-1))
val('8477',sum(2**k for k in range(8)),255); val('8478',sum(3**k for k in range(6)),364); val('8479',sum((-1)**(k+1)*2**k for k in range(8)),85)
# 8475: b1=2,bn=1458,S=2186: S=(bn*q-b1)/(q-1)
import sympy as sp
q=sp.symbols('q'); print('8475',sp.solve((1458*q-2)/(q-1)-2186,q),'8476',sp.solve((2401*q-1)/(q-1)-2801,q))
