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
    for a,b in [('\\arcctg','acot'),('\\sin','sin'),('\\cos','cos'),('\\tg','tan'),('\\ctg','cot'),('\\arcsin','asin'),('\\arccos','acos'),('\\arctg','atan')]: s=s.replace(a,b)
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
env={'acot':lambda u: math.pi/2-math.atan(u),'root':root,'lg':lg,'lg10':lambda u:lg(u,10),'ln':lambda u:lg(u,math.e),'abs':abs,'sin':math.sin,'cos':math.cos,'tan':math.tan,'cot':lambda u:1/math.tan(u),'asin':math.asin,'acos':math.acos,'atan':math.atan,'pi':math.pi,'math':math}
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

import itertools
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~ '^Решите уравнение' and question_latex ~ '(sin|cos|tg|ctg)' and question_latex like '%$%'")
rows=cur.fetchall(); print(len(rows))
res=[];checked=0;why={}
def fixarc(t):
    t=t.replace('\\operatorname{arctg}','\\arctan').replace('\\arctg','\\arctan').replace('\\operatorname{arcctg}','\\arccot').replace('\\arcctg','\\arccot').replace('\\operatorname{arccot}','\\arccot')
    t=t.replace('\\arcsin','\\asin ').replace('\\arccos','\\acos ').replace('\\arctan','\\atan ').replace('\\arccot','\\acot ')
    return t
def trx(t):
    t=fixarc(t)
    t=t.replace('\\asin','ASIN').replace('\\acos','ACOS').replace('\\atan','ATAN').replace('\\acot','ACOT')
    e=tr(t.replace('ASIN','\\sin').replace('ACOS','\\cos').replace('ATAN','\\tg').replace('ACOT','\\ctg'))
    return e
def to_py(t):
    t=t.replace('\\operatorname{arctg}','\\arctg').replace('\\operatorname{arcctg}','\\arcctg').replace('\\arctan','\\arctg').replace('\\arccot','\\arcctg').replace('\\operatorname{arccot}','\\arcctg')
    return tr(t)
for i,q,k in rows:
    ms=re.findall(r'\$\$?([^$]+)\$\$?',q)
    if len(ms)!=1 or '=' not in ms[0] or ms[0].count('=')!=1: why['ms']=why.get('ms',0)+1; continue
    L,R=ms[0].strip().rstrip('.;,').split('=')
    if re.search(r'\\begin|\\cases|\\text|<|>|\\le|\\ge',ms[0]): why['rel']=why.get('rel',0)+1; continue
    el=tr(L.replace('\\operatorname{\\tg }','\\tg').replace('\\operatorname{\\ctg}','\\ctg')); er=tr(R)
    if el is None or er is None: why['tr']=why.get('tr',0)+1; continue
    try: fl=make_f(el); fr=make_f(er)
    except SyntaxError: why['syn']=why.get('syn',0)+1; continue
    # key series
    kk=(k or '').strip()
    if re.search(r'нет|корней|решений|\\varnothing|\\emptyset',kk): why['nokey']=why.get('nokey',0)+1; continue
    kk=kk.replace('$','').replace('\\,',' ').replace('\\quad',' ')
    kk=re.sub(r'[,;]?\s*[kn m]\s*\\in\s*\\?(mathbb\{)?[ZR]\}?','',kk)
    kk=re.sub(r'\\in\s*\\mathbb\{Z\}','',kk)
    parts=[p for p in re.split(r'\s*;\s*|\s+или\s+|\s+и\s+',kk) if p.strip()]
    if len(parts)==1 and ',' in parts[0]:
        parts=[p for p in re.split(r'\s*,\s*(?=[^{}]*(?:x\s*=|\\pm|\\frac|[0-9]|\(-1\)))',parts[0]) if p.strip()]
    series=[]
    bad=False
    for p in parts:
        p=re.sub(r'^\s*x\s*=\s*','',p.strip()).strip().rstrip('.,;')
        if not p: continue
        variants=[p]
        if '\\pm' in p:
            variants=[p.replace('\\pm','+',1),p.replace('\\pm','-',1)]
        for v in variants:
            v=v.replace('\\pm','+')
            e=to_py(v)
            if e is None: bad=True;break
            # variable names k,n,m -> K
            e=re.sub(r'(?<![a-zA-Z])[knm](?![a-zA-Z(])','K',e)
            e=e.replace('(-1)**(','(-1)**(')
            series.append(e)
        if bad: break
    if bad or not series: why['key']=why.get('key',0)+1; continue
    try: sf=[compile(e,'<s>','eval') for e in series]
    except SyntaxError: why['ksyn']=why.get('ksyn',0)+1; continue
    pts=[]
    ok=True
    for c in sf:
        for K in range(-40,41):
            e=dict(env); e['K']=K
            try: v=eval(c,{'__builtins__':{}},e)
            except Exception: ok=False;break
            if isinstance(v,(int,float)) and -20<v<20: pts.append(v)
        if not ok: break
    if not ok: why['keval']=why.get('keval',0)+1; continue
    # check key points are roots
    def g(x): return fl(x)-fr(x)
    badpts=0;tested=0
    for v in pts:
        try:
            gv=g(v); tested+=1
            if not(math.isfinite(gv)) or abs(gv)>1e-6: badpts+=1
        except (ValueError,ZeroDivisionError,OverflowError): badpts+=1; tested+=1
        except (TypeError,NameError): tested=0;break
    if tested==0: why['evalg']=why.get('evalg',0)+1; continue
    # numeric roots
    N=80000; lo,hi=-20.0,20.0; xs=[lo+(hi-lo)*j/N for j in range(N+1)]
    vals=[]
    for x in xs:
        try: gv=g(x); vals.append(gv if math.isfinite(gv) else None)
        except Exception: vals.append(None)
    roots=[]
    for j in range(N):
        a,b=vals[j],vals[j+1]
        if a is None or b is None: continue
        if a==0: roots.append(xs[j]); continue
        if a*b<0 and abs(a)<30 and abs(b)<30:
            x1,x2=xs[j],xs[j+1]
            for _ in range(60):
                xm=(x1+x2)/2
                try: gm=g(xm)
                except Exception: break
                if gm is None or not math.isfinite(gm): break
                if g(x1)*gm<=0: x2=xm
                else: x1=xm
            xm=(x1+x2)/2
            try:
                if abs(g(xm))<1e-6: roots.append(xm)
            except Exception: pass
    missing=[r for r in roots if not any(abs(r-p)<1e-5 for p in pts)]
    checked+=1
    if badpts>0 or missing:
        res.append((i,'nonroot' if badpts else '', badpts,len(missing),[round(m,3) for m in missing[:3]],ms[0][:60],kk[:70]))
print('checked',checked,'flagged',len(res),why)
for r in res: print(r)
