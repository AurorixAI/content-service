import psycopg2,re,json
c=psycopg2.connect(host='algo-content-db',dbname='algo_content',user='algo',password='algo_password'); cur=c.cursor()
ids=['G11_TB_§2_2_12_а','G11_TB_§2_2_12_в','G11_TB_3_1_2_40_2','G11_TB_§3_2_40_2','G11_TB_2_2_52_4']
lines=['# -*- coding: utf-8 -*-','S = "сплошной скан: в пределах и функциях $\\\\sin\\\\frac{x}{x}$ вместо $\\\\frac{\\\\sin x}{x}$; проверено по ключам (замечательный предел равен 1)"','P = {}','def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)']
for i in ids:
    cur.execute("select question_latex from tasks_master where id=%s",(i,)); q=cur.fetchone()[0]
    nq=re.sub(r'\\sin\s*\\dfrac\{([^{}]+)\}\{\1\}',lambda m:'\\dfrac{\\sin '+m.group(1)+'}{'+m.group(1)+'}',q)
    print(i,'\n  ',q,'\n ->',nq)
    lines.append(f'E({i!r}, "в условии дробь $\\\\frac{{\\\\sin u}}{{u}}$ была записана как $\\\\sin\\\\frac{{u}}{{u}}$ (тождественно $\\\\sin 1$); ключ относится к $\\\\frac{{\\\\sin u}}{{u}}$", q={nq!r})')
open('fix_ctrl31.py','w').write('\n'.join(lines)+'\n')
