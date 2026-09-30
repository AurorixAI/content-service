import re,random,math,psycopg2
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
def brace(s,i):
    d=0
    for j in range(i,len(s)):
        if s[j]=='{': d+=1
        elif s[j]=='}':
            d-=1
            if d==0: return j
    return -1
def tr(s):
    s=s.replace('$','').strip().rstrip('.;,')
    s=s.replace('\\dfrac','\\frac').replace('\\left','').replace('\\right','').replace('\\cdot','*').replace('\\,','').replace('\\ ','').replace('\\pi','pi').replace('{,}','.')
    s=s.replace('\\operatorname{tg}','\\tg').replace('\\operatorname{ctg}','\\ctg').replace('\\mathrm{tg}','\\tg')
    # abs
    parts=s.split('|')
    if len(parts)%2==0: return None
    if len(parts)>1:
        s=parts[0]
        for j in range(1,len(parts)):
            s+=('abs(' if j%2==1 else ')')+parts[j]
    # frac
    for _ in range(40):
        m=re.search(r'\\frac\s*\{',s)
        if not m: break
        i=m.end()-1;j=brace(s,i)
        if j<0 or j+1>=len(s) or s[j+1]!='{': return None
        l=brace(s,j+1)
        s=s[:m.start()]+'(('+s[i+1:j]+')/('+s[j+2:l]+'))'+s[l+1:]
    for _ in range(40):
        m=re.search(r'\\sqrt\s*\[\s*(\d+)\s*\]\s*\{',s)
        if m:
            i=m.end()-1;j=brace(s,i); s=s[:m.start()]+'root('+s[i+1:j]+','+m.group(1)+')'+s[j+1:]; continue
        m=re.search(r'\\sqrt\s*\{',s)
        if m:
            i=m.end()-1;j=brace(s,i); s=s[:m.start()]+'root('+s[i+1:j]+',2)'+s[j+1:]; continue
        break
    # log_{b}
    for _ in range(10):
        m=re.search(r'\\log_\s*\{([^{}]+)\}\s*',s) or re.search(r'\\log_\s*([0-9a-z])\s*',s)
        if not m: break
        b=m.group(1)
        rest=s[m.end():]
        if rest.startswith('('):
            d=0
            for j,ch in enumerate(rest):
                if ch=='(': d+=1
                elif ch==')':
                    d-=1
                    if d==0: break
            arg=rest[1:j]; tail=rest[j+1:]
        elif rest.startswith('{'):
            j=brace(rest,0); arg=rest[1:j]; tail=rest[j+1:]
        else:
            mm=re.match(r'([a-z0-9.]+)',rest)
            if not mm: return None
            arg=mm.group(1); tail=rest[mm.end():]
        s=s[:m.start()]+'lg('+arg+','+b+')'+tail
    s=s.replace('\\lg','lg10').replace('\\ln','ln')
    for a,b in [('\\sin','sin'),('\\cos','cos'),('\\tg','tan'),('\\ctg','cot'),('\\arcsin','asin'),('\\arccos','acos'),('\\arctg','atan')]: s=s.replace(a,b)
    if '\\' in s: return None
    s=re.sub(r'\b(lg10|ln|sin|cos|tan|cot|asin|acos|atan)\s*\^\{?(\d+)\}?\s*([A-Za-z0-9(]+)',r'(\1(\3))**\2',s)
    s=re.sub(r'\b(lg10|ln|sin|cos|tan|cot|asin|acos|atan)\s+([A-Za-z0-9]+)',r'\1(\2)',s)
    s=s.replace('{','(').replace('}',')').replace('^','**')
    s=re.sub(r'(\d|\))\s*([a-zA-Z(])',r'\1*\2',s)
    s=re.sub(r'\)\s*\(',r')*(',s)
    s=re.sub(r'(?<![a-z])(x)(\()',r'\1*\2',s)
    s=re.sub(r'pi\s*(?=[a-zA-Z(\d])','pi*',s)
    return s
def root(u,n):
    if n%2==0:
        if u<0: raise ValueError
        return u**(1.0/n)
    return math.copysign(abs(u)**(1.0/n),u)
def lg(u,b):
    if u<=0 or b<=0 or b==1: raise ValueError
    return math.log(u)/math.log(b)
env={'root':root,'lg':lg,'lg10':lambda u:lg(u,10),'ln':lambda u:lg(u,math.e),'abs':abs,'sin':math.sin,'cos':math.cos,'tan':math.tan,'cot':lambda u:1/math.tan(u),'asin':math.asin,'acos':math.acos,'atan':math.atan,'pi':math.pi,'math':math}
def make_f(expr):
    code=compile(expr,'<f>','eval')
    def f(x):
        e=dict(env); e['x']=x
        return eval(code,{'__builtins__':{}},e)
    return f
def bound(s):
    s=s.strip().replace('+\\infty','\\infty')
    if s=='-\\infty': return -1e18
    if s=='\\infty': return 1e18
    t=tr(s)
    if t is None: return None
    try: return float(eval(t,{'__builtins__':{}},dict(env)))
    except Exception: return None
def key_member(k):
    k0=k
    k=k.replace('\\left','').replace('\\right','').replace('\\dfrac','\\frac')
    holes=[]
    for m in re.finditer(r'кроме\s*\$?\s*x\s*=\s*([-0-9{},.]+)\s*\$?',k):
        b=bound(m.group(1)); 
        if b is None: return None
        holes.append(b)
    k=re.sub(r'кроме\s*\$?\s*x\s*=\s*[-0-9{},.]+\s*\$?','',k)
    for m in re.finditer(r'\\setminus\s*\\\{([^}]*)\\\}',k):
        for h in m.group(1).split(','):
            b=bound(h)
            if b is None: return None
            holes.append(b)
    k=re.sub(r'\\setminus\s*\\\{[^}]*\\\}','',k)
    if re.search(r'все числа|любое число|\\mathbb\{R\}|\(-\\infty;\s*\+?\\infty\)',k) and 'cup' not in k:
        return lambda x: not any(abs(x-h)<1e-9 for h in holes)
    ivs=[]
    for m in re.finditer(r'([\(\[])\s*([^;\[\]\(\)]+?)\s*;\s*([^;\[\]\(\)]+?)\s*([\)\]])',k):
        lo=bound(m.group(2)); hi=bound(m.group(3))
        if lo is None or hi is None: return None
        ivs.append((m.group(1),lo,hi,m.group(4)))
    pts=[]
    for m in re.finditer(r'\\\{([^}]*)\\\}',k0):
        pts+= [bound(h) for h in m.group(1).split(',')]
    if ivs or pts:
        if None in pts: return None
        return lambda x: (not any(abs(x-h)<1e-9 for h in holes)) and (any((x>lo if a=='(' else x>=lo) and (x<hi if b==')' else x<=hi) for a,lo,hi,b in ivs) or any(abs(x-p)<1e-9 for p in pts))
    # inequalities
    kk=k.replace('$','')
    kk=kk.replace('\\ge','>=').replace('\\geq','>=').replace('\\le','<=').replace('\\leq','<=').replace('\\neq','!=').replace('\\ne','!=')
    cons=[]
    parts=re.split(r'\s*(?:,|;|\bи\b)\s*',kk)
    orparts=re.split(r'\s+или\s+',kk)
    def atom(p):
        m=re.fullmatch(r'\s*x\s*(>=|<=|!=|>|<|=)\s*([-0-9{}.,\\a-z]+)\s*',p.strip().rstrip('.'))
        if not m: return None
        b=bound(m.group(2))
        if b is None: return None
        op=m.group(1)
        return {'>=':lambda x:x>=b-1e-12,'<=':lambda x:x<=b+1e-12,'!=':lambda x:abs(x-b)>1e-9,'>':lambda x:x>b,'<':lambda x:x<b,'=':lambda x:abs(x-b)<1e-9}[op]
    if len(orparts)>1:
        at=[atom(p) for p in orparts]
        if None in at: return None
        return lambda x: (not any(abs(x-h)<1e-9 for h in holes)) and any(a(x) for a in at)
    at=[atom(p) for p in parts if p.strip()]
    if not at or None in at: return None
    return lambda x: (not any(abs(x-h)<1e-9 for h in holes)) and all(a(x) for a in at)

cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~* '(сумму всех целых|сколько целых|наименьшее целое|наибольшее целое|количество целых|целых решений|целых значений|всех целых)' and question_latex like '%$%'")
rows=cur.fetchall(); print(len(rows))
OPS=[('\\leqslant','<='),('\\geqslant','>='),('\\leq','<='),('\\geq','>='),('\\le','<='),('\\ge','>='),('<','<'),('>','>')]
def split_rel(t):
    t=t.strip().rstrip(';.,')
    for tok,op in OPS:
        parts=t.split(tok)
        if len(parts)==2 and not any(x in parts[0]+parts[1] for x in ['\\le','\\ge','<','>']):
            return parts[0],op,parts[1]
    return None
def atom_fn(t):
    sr=split_rel(t)
    if sr is None: return None
    L,op,R=sr
    el=tr(L); er=tr(R)
    if el is None or er is None: return None
    try: fl=make_f(el); fr=make_f(er)
    except SyntaxError: return None
    def fn(x):
        try:
            lv=fl(x); rv=fr(x)
            if not(isinstance(lv,(int,float)) and isinstance(rv,(int,float)) and math.isfinite(lv) and math.isfinite(rv)): return False
        except (ValueError,ZeroDivisionError,OverflowError,NameError,TypeError): return False
        return {'<':lv<rv-1e-9,'<=':lv<=rv+1e-9,'>':lv>rv+1e-9,'>=':lv>=rv-1e-9}[op]
    return fn
res=[];checked=0;why={}
for i,q,k in rows:
    body=q
    fns=[]
    m=re.search(r'\\begin\{(?:cases|array)\}(?:\{[^}]*\})?(.+?)\\end\{(?:cases|array)\}',q,re.S)
    if m:
        rs=[r.strip() for r in re.split(r'\\\\',m.group(1)) if r.strip()]
        rs=[re.sub(r'&|\[[0-9a-z]+\]','',r).strip().rstrip(',;.') for r in rs]
        fs=[atom_fn(r) for r in rs]
        if None in fs: why['sysparse']=why.get('sysparse',0)+1; continue
        fns=fs
    else:
        ms=re.findall(r'\$\$?([^$]+)\$\$?',q)
        if len(ms)<1: why['nomath']=why.get('nomath',0)+1; continue
        # single inequality, possibly with 2 (system in inline): take all math pieces that are relations
        fs=[]
        for t in ms:
            if split_rel(t) is None: continue
            f=atom_fn(t)
            if f is None: fs=None;break
            fs.append(f)
        if not fs: why['noineq']=why.get('noineq',0)+1; continue
        fns=fs
    mk=re.fullmatch(r'\$?\s*(-?\d+)\s*\$?\.?',(k or '').strip())
    if not mk: why['keynum']=why.get('keynum',0)+1; continue
    kv=int(mk.group(1))
    lo,hi=-2000,2000
    mr=re.search(r'\[\s*(-?\d+)\s*;\s*(-?\d+)\s*\]',q) or re.search(r'\((-?\d+)\s*;\s*(-?\d+)\)',q)
    if mr and re.search(r'из (отрезка|промежутка|интервала)|на (отрезке|промежутке)',q):
        lo,hi=int(mr.group(1)),int(mr.group(2))
        if mr.group(0)[0]=='(': lo+=1
        if mr.group(0)[-1]==')': hi-=1
    try: sol=[n for n in range(lo,hi+1) if all(f(n) for f in fns)]
    except Exception: why['evalerr']=why.get('evalerr',0)+1; continue
    if re.search(r'сумм',q): val=sum(sol)
    elif re.search(r'[Сс]колько|количеств',q): val=len(sol)
    elif re.search(r'наименьш',q): val=min(sol) if sol else None
    elif re.search(r'наибольш',q): val=max(sol) if sol else None
    else: why['kind']=why.get('kind',0)+1; continue
    checked+=1
    if val!=kv: res.append((i,val,kv,re.sub(r'\s+',' ',q)[:110]))
print('checked',checked,'mismatch',len(res),why)
for r in res: print(r)
