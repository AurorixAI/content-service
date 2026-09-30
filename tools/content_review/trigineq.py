import re,random,math,json
exec(open('exprscan2.py').read().split("cur.execute(\"select id,correct_answer_latex")[0])
import sympy as sp
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~ 'Решите неравенство' and question_latex ~ '(sin|cos|tg|ctg|tan|cot)' and correct_answer_latex ~ '(pi|\\\\pi)'")
rows=cur.fetchall(); print(len(rows))
def parse_q(q):
    m=re.findall(r'\$([^$]+)\$',q)
    if len(m)!=1: return None
    t=m[0].strip()
    mm=re.fullmatch(r'(.+?)\s*(\\leqslant|\\geqslant|\\leq|\\geq|\\le|\\ge|<|>)\s*(.+)',t)
    if not mm: return None
    L,op,R=mm.groups()
    op={'\\leqslant':'<=','\\le':'<=','\\leq':'<=','\\geqslant':'>=','\\ge':'>=','\\geq':'>=','<':'<','>':'>'}[op]
    l=parse(L); r=parse(R)
    if l is None or r is None: return None
    return l,op,r
def parse_expr_k(s):
    s=s.strip()
    e=parse(s)
    return e
def key_intervals(k):
    k=k.replace('\\left','').replace('\\right','').replace('\\dfrac','\\frac')
    ivs=[]
    for m in re.finditer(r'([\(\[])\s*([^;\[\]\(\)]*?(?:\([^()]*\)[^;\[\]\(\)]*?)*)\s*;\s*([^\[\]\(\)]*?(?:\([^()]*\)[^\[\]\(\)]*?)*)\s*([\)\]])',k):
        ivs.append((m.group(1),m.group(2),m.group(3),m.group(4)))
    return ivs
res=[];checked=0
kk=sp.Symbol('k'); nn=sp.Symbol('n')
for i,q,k in rows:
    pq=parse_q(q)
    if pq is None: continue
    l,op,r=pq
    xs=[s for s in (l.free_symbols|r.free_symbols)]
    if len(xs)!=1 or xs[0].name!='x': continue
    x=xs[0]
    kt=k.replace('n \\in','k \\in')
    kt=re.sub(r'\bn\b','k',kt) if 'k' not in kt else kt
    ivs=key_intervals(kt.replace('\\pi n','\\pi k'))
    if not ivs: continue
    parsed=[]
    okp=True
    for a,lo,hi,b in ivs:
        lo=lo.replace('\\pi n','\\pi k'); hi=hi.replace('\\pi n','\\pi k')
        elo=parse(lo.replace('+\\infty','')) ; ehi=parse(hi)
        if elo is None or ehi is None: okp=False;break
        parsed.append((a,elo,ehi,b))
    if not okp: continue
    def member(xv):
        for a,elo,ehi,b in parsed:
            for kv in range(-12,13):
                syms=sorted((elo.free_symbols|ehi.free_symbols),key=lambda s:s.name)
                kn=[s for s in syms if s.name=='k']
                sub={s:(kv if s.name=='k' else 0) for s in syms}
                try:
                    lo=float(elo.subs(sub)); hi=float(ehi.subs(sub))
                except Exception: continue
                ok=(xv>lo if a=='(' else xv>=lo) and (xv<hi if b==')' else xv<=hi)
                if ok: return True
        return False
    fl=sp.lambdify(x,l,'math'); fr=sp.lambdify(x,r,'math')
    mism=0;tot=0;ex=None
    random.seed(5)
    for _ in range(400):
        xv=random.uniform(-9,9)
        try:
            lv=fl(xv); rv=fr(xv)
        except Exception: continue
        if not(math.isfinite(lv) and math.isfinite(rv)): continue
        if abs(lv-rv)<1e-6: continue
        truth={'<':lv<rv,'<=':lv<=rv,'>':lv>rv,'>=':lv>=rv}[op]
        tot+=1
        if truth!=member(xv):
            mism+=1
            if ex is None: ex=round(xv/math.pi,3)
    checked+=1
    if tot>=50 and mism>0: res.append((i,mism,tot,ex,re.sub(r'\s+',' ',q)[:80],k[:90]))
print('checked',checked,'mismatch',len(res))
for r_ in res: print(r_)
