import math
def f(x):
    a=2**x-3
    if a<=0: return None
    b=4**(x+2)-12*2**(x+3)+144
    if b<=0: return None
    return math.log2(a)*(math.log2(b)/0.5)
import numpy as np
xs=np.linspace(1.5,4,25001); segs=[];prev=None
for x in xs:
    v=f(x); ok=v is not None and v<32
    if ok and prev is None: st=x
    if not ok and prev is not None: segs.append((st,last))
    prev=x if ok else None; last=x
if prev is not None: segs.append((st,last))
print(segs, math.log2(49/16), math.log2(7), math.log2(3), math.log2(12))
