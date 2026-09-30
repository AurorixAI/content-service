import psycopg2
from fractions import Fraction as F
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
for t in ['G6_TB_34–37_298','G6_TB_51–52_450']:
    cur.execute("select correct_answer_latex from tasks_master where id=%s",(t,)); print(t, cur.fetchone()[0]); print()
def mx(w,n,dn): return F(w)+F(n,dn)
def show(x):
    w=int(x); f=x-w
    return f"{w} {f.numerator}/{f.denominator}" if w and f else (str(w) if not f else f"{f.numerator}/{f.denominator}")
a=[mx(10,7,10),mx(9,3,7),mx(15,9,10),None,mx(5,7,20),None,mx(4,3,10)]
b=[mx(3,1,5),None,None,mx(4,3,5),mx(3,3,10),mx(1,5,8),None]
s=[None,mx(14,2,21),None,F(23),None,None,mx(7,3,5)]
dd=[None,None,mx(2,3,100),None,None,mx(6,3,4),None]
for i in range(7):
    A,B,Sm,Df=a[i],b[i],s[i],dd[i]
    if A is not None and B is not None: Sm=A+B; Df=A-B
    elif A is not None and Sm is not None: B=Sm-A; Df=A-B
    elif A is not None and Df is not None: B=A-Df; Sm=A+B
    elif B is not None and Sm is not None: A=Sm-B; Df=A-B
    elif B is not None and Df is not None: A=B+Df; Sm=A+B
    print(i+1,'a',show(A),'b',show(B),'a+b',show(Sm),'a-b',show(Df))
print('--450')
a=[F(7,9),mx(1,3,5),None,F(5),mx(1,24,25),mx(8,1,3),F(7,10),None]
b=[F(3,7),None,F(5,14),None,mx(1,2,3),None,None,mx(5,1,3)]
p=[None,None,F(1),F(10),None,F(1),mx(3,1,3),None]
q=[None,mx(2,1,2),None,None,None,None,None,F(8)]
for i in range(8):
    A,B,Pp,Q=a[i],b[i],p[i],q[i]
    if A is not None and B is not None: Pp=A*B;Q=A/B
    elif A is not None and Pp is not None: B=Pp/A; Q=A/B
    elif B is not None and Pp is not None: A=Pp/B; Q=A/B
    elif A is not None and Q is not None: B=A/Q; Pp=A*B
    elif B is not None and Q is not None: A=Q*B; Pp=A*B
    print(i+1,'a',show(A),'b',show(B),'ab',show(Pp),'a:b',show(Q))
