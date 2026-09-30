import psycopg2,re
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
cur.execute("select id,question_latex,correct_answer_latex from tasks_master where is_active and question_latex ~ 'Сравните|сравните' and correct_answer_latex ~ '\\^'")
def ev(s):
    s=s.replace('$','').replace('{,}','.').replace('\\cdot','*').replace('\\dfrac','\\frac').strip()
    s=re.sub(r'\\frac\{(-?[\d.]+)\}\{(-?[\d.]+)\}',r'(\1/\2)',s)
    s=re.sub(r'\^\{([^{}]+)\}',r'**(\1)',s); s=s.replace('^','**')
    s=re.sub(r'(\d)\s*\(',r'\1*(',s)
    if re.search(r'[a-zA-Z\\]',s): return None
    try: return eval(s)
    except Exception: return None
bad=0;n=0
for i,q,k in cur.fetchall():
    m=re.split(r'(<|>|=)',k.replace('$',''))
    if len(m)!=3: continue
    a,b=ev(m[0]),ev(m[2])
    if a is None or b is None: continue
    n+=1
    ok={'<':a<b,'>':a>b,'=':a==b}[m[1]]
    if not ok: bad+=1; print('BAD',i,q[-70:].replace('\n',' '),'|',k,'|',a,b)
print(n,bad)
