import re,random,math
exec(open('exprscan2.py').read().split("cur.execute(\"select id,correct_answer_latex")[0])
import sympy as sp
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~ 'бласть определения' and question_latex like '%$%'")
rows=cur.fetchall(); print(len(rows))
def parse_bound(s):
    s=s.strip().replace('+\\infty','\\infty')
    if s in ('-\\infty','- \\infty'): return -1e18
    if s=='\\infty': return 1e18
    e=parse(s)
    if e is None or e.free_symbols: return None
    try: return float(e)
    except Exception: return None
def key_set(k):
    k=k.replace('\\left','').replace('\\right','').replace('\\dfrac','\\frac')
    if re.search(r'\\mathbb\{R\}\s*$|\(-\\infty;\s*\+?\\infty\)',k) and 'cup' not in k and 'setminus' not in k: return [('(',-1e18,1e18,')')],[]
    holes=[]
    for m in re.finditer(r'\\setminus\s*\\\{([^}]*)\\\}',k):
        for h in m.group(1).split(','):
            b=parse_bound(h)
            if b is None: return None
            holes.append(b)
    k2=re.sub(r'\\setminus\s*\\\{[^}]*\\\}','',k)
    ivs=[]
    for m in re.finditer(r'([\(\[])\s*([^;\[\]\(\)]+?)\s*;\s*([^;\[\]\(\)]+?)\s*([\)\]])',k2):
        lo=parse_bound(m.group(2)); hi=parse_bound(m.group(3))
        if lo is None or hi is None: return None
        ivs.append((m.group(1),lo,hi,m.group(4)))
    if not ivs: return None
    return ivs,holes
res=[];checked=0;why={}
random.seed(11)
for i,q,k in rows:
    ms=re.findall(r'\$\$?([^$]+)\$\$?',q)
    if not ms:
        why['noms']=why.get('noms',0)+1; continue
    t=ms[-1].strip()
    t=re.sub(r'^[a-zA-Zа-я]\)\s*','',t)
    m=re.match(r'^(?:y|f\(x\)|f)\s*=\s*(.+)$',t)
    if not m:
        why['nomatch']=why.get('nomatch',0)+1
        if why['nomatch']<12: print('NOMATCH',i,t[:90])
        continue
    e=parse(m.group(1))
    if e is None:
        why['noparse']=why.get('noparse',0)+1
        if why['noparse']<12: print('NOPARSE',i,m.group(1)[:90])
        continue
    xs=[s for s in e.free_symbols]
    if len(xs)!=1 or xs[0].name!='x':
        why['vars']=why.get('vars',0)+1; continue
    ks=key_set(k)
    if ks is None:
        why['key']=why.get('key',0)+1
        if why['key']<14: print('KEYFAIL',i,k[:90])
        continue
    ivs,holes=ks
    f=sp.lambdify(xs[0],e,'math')
    def defined(xv):
        try:
            v=f(xv)
            return isinstance(v,(int,float)) and math.isfinite(v)
        except Exception: return False
    def inkey(xv):
        if any(abs(xv-h)<1e-9 for h in holes): return False
        for a,lo,hi,b in ivs:
            if (xv>lo if a=='(' else xv>=lo) and (xv<hi if b==')' else xv<=hi): return True
        return False
    mism=0;tot=0;ex=None
    pts=[random.uniform(-12,12) for _ in range(500)]+[i/4 for i in range(-48,49)]
    for xv in pts:
        d=defined(xv); kk=inkey(xv); tot+=1
        if d!=kk:
            mism+=1
            if ex is None: ex=round(xv,3)
    checked+=1
    if mism>0: res.append((i,mism,tot,ex,t[:70],k[:80]))
print('checked',checked,'mismatch',len(res))
for r in res: print(r)

print(why)
