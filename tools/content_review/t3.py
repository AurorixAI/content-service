import math
def cbrt(v): return math.copysign(abs(v)**(1/3),v)
def roots(g,lo,hi,step=0.0005):
    out=[];x=lo;prev=None
    while x<=hi:
        try: v=g(x)
        except (ValueError,ZeroDivisionError): v=None
        if v is not None and prev is not None and prev*v<=0:
            a,b=x-step,x
            for _ in range(60):
                m=(a+b)/2
                try:
                    if g(a)*g(m)<=0:b=m
                    else:a=m
                except: break
            out.append(round((a+b)/2,4))
        prev=v;x+=step
    return sorted(set(out))
E={
'5847':(lambda x:cbrt(297-3*x)+math.sqrt(x-18)-9,18,600),
'5848':(lambda x:cbrt(192+4*x)+math.sqrt(-32-x)-4,-400,-32),
'5849':(lambda x:cbrt(3*x+20)+cbrt(5*x+4)-cbrt(2*x+19)-cbrt(6*x+5),-50,50),
'5850':(lambda x:cbrt(x+6)+cbrt(7*x+10)-cbrt(2*x+15)-cbrt(6*x+1),-50,50),
'5851':(lambda x:cbrt(2*x+5)+cbrt(5*x+16)-cbrt(x+8)-cbrt(6*x+13),-50,50),
'5852':(lambda x:cbrt(4*x+6)+cbrt(5*x+12)-cbrt(3*x+10)-cbrt(6*x+8),-50,50),
'5853':(lambda x:cbrt(x-2)+cbrt(x+5)-cbrt(30-x),-100,100),
'5854':(lambda x:cbrt(x-1)+cbrt(2*x+4)-cbrt(31-2*x),-100,100),
'5856':(lambda x:math.sqrt(4*x-x*x)+math.sqrt(4*x-x*x-3)-3-math.sqrt(2*x-x*x),1,2),
'5837':(lambda x:math.sqrt(629-x)+math.sqrt(77+x)-8,-77,629),
}
for k,(g,lo,hi) in E.items(): print(k,roots(g,lo,hi))
