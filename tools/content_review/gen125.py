# -*- coding: utf-8 -*-
import subprocess, re, json
from fractions import Fraction as F
def sql(t):
    return subprocess.check_output(["docker","exec","algo-content-db","psql","-U","algo","-d","algo_content","-At","-F","\x1f","-c",
      "select id,question_latex,correct_answer_latex from tasks_master where id='%s'"%t]).decode().strip().split("\x1f")
def fmt(x):
    x=F(x)
    if x.denominator==1: return "$%d$"%x.numerator
    d=x.denominator
    while d%2==0: d//=2
    while d%5==0: d//=5
    if d==1:
        s=("%.4f"%float(x)).rstrip("0").replace(".","{,}").replace("-","-")
        return "$%s$"%s
    sg="-" if x<0 else ""
    return r"$%s\dfrac{%d}{%d}$"%(sg,abs(x.numerator),x.denominator)
def fnum(x):
    return fmt(x)[1:-1]
def nums(q):
    body=q.split(":",1)[1] if ":" in q else q
    body=body.replace("–","-").replace("$","")
    return [int(v) for v in re.findall(r"-?\d+",body)]
out=[]
def P(s): out.append(s)
P('# -*- coding: utf-8 -*-\nS = "полный обзор задач 9 класса (очередь G9), проверено вычислением и ответами учебника"\nP = {}\ndef E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)\n')
ids=["G9_TB_38_492_3","G9_TB_38_492_4","G9_TB_38_493_1","G9_TB_38_493_2","G9_TB_УКГ5_504_1","G9_TB_УКГ5_504_2","G9_TB_УКГ5_505_1","G9_TB_УКГ5_505_2","G9_TB_УКГ5_506_1","G9_TB_УКГ5_506_2","G9_TB_УКГ5_507_1","G9_TB_УКГ5_507_2"]
DEF="(среднее арифметическое её значений)"
for t in ids:
    _,q,k=sql(t)
    s=nums(q); n=len(s); ss=sorted(s)
    mean=F(sum(s),n); mid=F(ss[0]+ss[-1],2)
    med=F(ss[n//2]) if n%2 else F(ss[n//2-1]+ss[n//2],2)
    q2=q.replace("середину выборки:","середину выборки "+DEF+":")
    assert q2!=q
    why=("«середина выборки» в задачнике — среднее арифметическое (ответ 492.2 = −5,4 = среднее; ответ 505.2 = 3 = среднее, а не полусумма крайних 3,5); "
         "среднее %s ; в ключе стояло другое число (полусумма крайних/медиана)")%fnum(mean)
    if re.match(r"^\$?\d+\$?$",k) or k.startswith("$"):
        # только середина
        newk=fmt(mean)
        cand=[(fmt(mid),"Ученик принял серединой полусумму наименьшего и наибольшего значений: $(%d+%d):2$; но середина выборки — среднее арифметическое всех значений."%(ss[0],ss[-1])),
              (fmt(med),"Ученик нашёл медиану (%s) вместо среднего арифметического: середина выборки — сумма значений, делённая на их число, а не средний по порядку элемент."%fnum(med)),
              (fmt(F(sum(s))),"Ученик сложил все значения (сумма равна $%d$) и не разделил на их число $%d$."%(sum(s),n))]
        kk=newk
        d=[(v,w) for v,w in cand]
    else:
        m=re.search(r"; середина: .*$|, середина .*$",k)
        head=k[:m.start()]; sep=m.group(0)[:m.group(0).index("середина")]
        mk=lambda x: head+sep+"середина"+(": " if sep.startswith(";") else " ")+fmt(x)
        kk=mk(mean)
        d=[(mk(mid),"Ученик принял серединой полусумму наименьшего и наибольшего значений: $(%d+%d):2$; середина выборки — среднее арифметическое всех значений."%(ss[0],ss[-1])),
           (mk(med),"Ученик принял за середину выборки её медиану (%s); середина выборки — сумма всех значений, делённая на их число."%fnum(med)),
           (mk(F(sum(s))),"Ученик сложил все значения (сумма равна $%d$) и не разделил на их число $%d$; середина выборки — их среднее арифметическое."%(sum(s),n))]
    from collections import Counter
    cn=Counter(s); mo=min(v for v,c in cn.items() if c==max(cn.values()))
    pool_extra=[(F(mo),"Ученик принял за середину выборки моду (%d); середина выборки — среднее арифметическое всех значений."%mo),
                (F(ss[-1]-ss[0],2),"Ученик разделил пополам размах (%d) вместо вычисления среднего арифметического значений выборки."%(ss[-1]-ss[0]))]
    seen={kk}; dd=[]
    for v,w in d:
        if v not in seen: seen.add(v); dd.append((v,w))
    for x,w in pool_extra:
        if len(dd)>=3: break
        v=(fmt(x) if (re.match(r"^\$?\d+\$?$",k) or k.startswith("$")) else mk(x))
        if v not in seen: seen.add(v); dd.append((v,w))
    d=dd[:3]
    assert len(d)==3,(t,d)
    if t=="G9_TB_УКГ5_507_1":
        P("# 507_1: ключ верен (0,75), только уточнение в условии\nE(%r, r%r, q=r%r)\n"%(t,"уточнено определение «середина» (среднее арифметическое); ключ верен: сумма $6$, $6:8=0{,}75$",q2))
        continue
    P("E(%r, r%r,\n  q=r%r,\n  k=r%r,\n  dnew={%s})\n"%(t,why,q2,kk,", ".join("%d: (r%r, r%r)"%(i,v,w) for i,(v,w) in enumerate(d))))
open("specs/fix_ctrl125.py","w").write("\n".join(out))
