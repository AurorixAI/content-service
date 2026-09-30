from sympy import *
import math
x,y=symbols('x y')
print(solve([x**3-64*y**3-56,x**2*y-4*x*y**2-4],[x,y]))
# G11 10_1_4: x^11 - x^6 + 2x + 4 < 0
f=lambda t:t**11-t**6+2*t+4
for t in [-3,-1.5,-1.01,-1,-0.99,-0.5,0,0.5,1,2]: print(t,f(t)<0, round(f(t),4))
# S217 inequality numeric
def g(t):
    b=t*t-2*t-3
    if b<=0 or b==1: return None
    if (t+4)/(t+1)<=0: return None
    if (t*t-2*t-2)==0: return None
    L=2+math.log((t+4)/(t+1))/math.log(math.sqrt(b))
    R=math.log((t*t-2*t-2)**2)/math.log(b)
    return L>R+1e-12
import numpy as np
xs=np.linspace(-6,8,28001); sol=[t for t in xs if g(t)]
# report intervals
prev=None; segs=[]
for t in xs:
    v=g(t)
    if v and prev is None: start=t
    if not v and prev is not None: segs.append((start,last))
    prev=t if v else None; last=t
if prev is not None: segs.append((start,last))
print(segs)
print(1+math.sqrt(5),10/3)
