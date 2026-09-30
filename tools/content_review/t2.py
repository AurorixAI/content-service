from fractions import Fraction as F
import math
def f(x): 
    x=x%8
    return 8*x-x*x
sol=[]
for i in range(-160,161):
    x=F(i,8)
    # test rational grid and exact
    if f(2*x+16)+23==5*f(x): sol.append(x)
print([str(s) for s in sol if -16<=s<=16])
# also check roots on fine grid for non-eighth roots via sign changes
g=lambda x:f(2*x+16)+23-5*f(x)
import itertools
prev=None;xs=[i/1000 for i in range(0,16001)]
sc=[round(xs[i],3) for i in range(1,len(xs)) if g(xs[i-1])*g(xs[i])<0]
print(sc)
ks=[k for k in range(-2,200) if k!=0 and (1+4*k>=0) and math.isqrt(1+4*k)**2==1+4*k]
print(ks[:8],[n*(n+1) for n in range(0,8)])
