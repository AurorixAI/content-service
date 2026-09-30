import math
def roots(g,lo,hi,n=400000):
    out=[];xs=[lo+(hi-lo)*i/n for i in range(n+1)];pv=None
    for x in xs:
        try: v=g(x)
        except: v=None
        if v is not None and abs(v)<1e-9: out.append(round(x,4))
        elif v is not None and pv is not None and pv*v<0:
            out.append(round(x,3))
        pv=v
    return sorted(set(out))
E={
'6068':lambda x:2**(x+3)+2**(2*x+1)-7*3**x-3,
'6077':lambda x:3*2**(x+2)+5**x-8*3**x-5,
'6078':lambda x:3*2**x-3**(x+1)+4**x-1,
'6079':lambda x:3*2**(x+4)+6*7**(x+1)-3*5**(x+2)-15,
}
for k,g in E.items(): print(k,roots(g,-12,12))
