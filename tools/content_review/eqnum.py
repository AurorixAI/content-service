import psycopg2,re,sympy as sp
from fractions import Fraction
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,correct_answer_latex,distractor_meta from tasks_master where is_active")
def conv(s):
    s=s.replace('{,}','.').replace('\\cdot','*').replace('\\times','*').replace('\\div','/').replace(':','/').replace('\\left','').replace('\\right','').replace('\\,','').replace('−','-').replace('\\ ','').replace('~','')
    s=re.sub(r'\\d?frac\{([^{}]+)\}\{([^{}]+)\}',r'((\1)/(\2))',s)
    s=s.replace('{','(').replace('}',')').replace('^','**')
    return s
pat=re.compile(r'^\$?\s*([0-9.,+\-*/():\\a-z{}\[\] ^ ]+?)\s*=\s*(-?[0-9][0-9. {},]*)\s*\$?[.;]?$')
n=0;chk=0
for i,k,d in cur.fetchall():
    vals=[('K',k)]+[(f'D{j}',x.get('value_latex') or x.get('value')) for j,x in enumerate(d or [])]
    for lab,v in vals:
        v=(v or '').strip().strip('$').strip()
        if v.count('=')!=1 or re.search(r'[a-zA-Zа-я]',re.sub(r'\\(cdot|times|div|left|right|dfrac|frac)','',v)): continue
        lhs,rhs=v.split('=')
        try:
            L=sp.nsimplify(sp.sympify(conv(lhs))); R=sp.nsimplify(sp.sympify(conv(rhs)))
        except Exception: continue
        chk+=1
        if abs(float(L-R))>1e-9:
            n+=1; print(i,lab,v[:100],'| lhs=',L)
print(chk,n)
