import sympy as sp
a,d=sp.symbols('a d',real=True)
for n,s4 in ((6,49),(7,51)):
    t=[a+i*d for i in range(n)]
    sols=sp.solve([sum(x**5 for x in t), sum(x**4 for x in t)-s4],[a,d],dict=True)
    for s in sols:
        try:
            av=sp.N(s[a]);dv=sp.N(s[d])
        except: continue
        if av.is_real and dv.is_real: print(n,av,dv,[sp.N(a.subs(s)+i*dv) for i in (0,n-1)])
