import psycopg2,re,json
from fractions import Fraction as F
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
def val(s):
    s=s.strip().strip('$').strip().rstrip('.;,').strip()
    s=s.replace('\\left','').replace('\\right','').replace('{,}','.').replace(',','.').replace('\\,','').replace(' ','').replace('\\dfrac','\\frac').replace('\\!','')
    s=s.replace('−','-')
    m=re.fullmatch(r'(-?)(\d+)\\frac\{(\d+)\}\{(\d+)\}',s)
    if m: return (-1 if m.group(1) else 1)*(F(int(m.group(2)))+F(int(m.group(3)),int(m.group(4))))
    m=re.fullmatch(r'-?\\frac\{-?\d+\}\{-?\d+\}',s)
    if m:
        mm=re.fullmatch(r'(-?)\\frac\{(-?\d+)\}\{(-?\d+)\}',s); return (-1 if mm.group(1) else 1)*F(int(mm.group(2)),int(mm.group(3)))
    m=re.fullmatch(r'-?\d+(\.\d+)?',s)
    if m: return F(s)
    m=re.fullmatch(r'\((-?\d+(\.\d+)?)\)\^\{?(\d+)\}?',s)
    if m: return F(m.group(1))**int(m.group(3))
    return None
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~ '^Сравните' and correct_answer_latex ~ '[<>=]'")
bad=[]; tot=0
for i,q,k in cur.fetchall():
    body=re.sub(r'^Сравните[^$:]*','',q,count=1).strip().rstrip('.;')
    # operands in statement: split by ' и '
    body=body.replace('$','').strip(': ')
    parts=re.split(r'\s+и\s+',body)
    if len(parts)!=2: continue
    qa,qb=val(parts[0]),val(parts[1])
    m=re.split(r'(<|>|=|\\leq|\\geq|\\le|\\ge)',k.replace('$',''))
    if len(m)!=3: continue
    ka,kb=val(m[0]),val(m[2])
    if None in (qa,qb,ka,kb): continue
    tot+=1
    op=m[1]
    truth={'<':ka<kb,'>':ka>kb,'=':ka==kb}.get(op)
    if {qa,qb}!={ka,kb} or truth is False:
        bad.append((i,q[-60:].replace('\n',' '),k[:60],{qa,qb}!={ka,kb},truth is False))
print(tot,len(bad))
for b in bad: print(b)
json.dump([b[0] for b in bad],open('cmp_bad.json','w'))
