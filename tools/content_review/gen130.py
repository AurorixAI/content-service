# -*- coding: utf-8 -*-
import subprocess
def row(t):
    return subprocess.check_output(["docker","exec","algo-content-db","psql","-U","algo","-d","algo_content","-At","-F","\x1f","-c",
      "select question_latex,correct_answer_latex from tasks_master where id='%s'"%t]).decode().rstrip("\n").split("\x1f")
CL=r"(главный аргумент — из промежутка $(-\pi; \pi]$)"
o=['# -*- coding: utf-8 -*-\nS = "соглашение об аргументе комплексного числа (решение владельца 2026-09-30)"\nP = {}\ndef E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)\n']
WHY="учебник берёт главный аргумент из $[0; 2\\pi)$, ключи банка — из $(-\\pi; \\pi]$; промежуток указан в условии, чтобы ответ был однозначным"
for t,old,new in [("G11_TB_17_1*_17_3","укажите его главный аргумент:","укажите его главный аргумент "+CL+":"),
                  ("G11_TB_17_1*_17_4","укажите его главный аргумент:","укажите его главный аргумент "+CL+":"),
                  ("G11_TB_17_1*_17_5","укажите его главный аргумент:","укажите его главный аргумент "+CL+":"),
                  ("G11_TB_17_1*_17_6","укажите его главный аргумент:","укажите его главный аргумент "+CL+":"),
                  ("G11_TB_2_1_3","найдите его модуль и аргумент","найдите его модуль и аргумент "+CL),
                  ("G11_TB_2_2","можно найти его модуль и аргумент","можно найти его модуль и аргумент "+CL)]:
    q,k=row(t); assert q.count(old)==1,(t,old)
    kw=dict(q=q.replace(old,new))
    why=WHY
    if t.endswith("17_6"):
        ko=r"$\varphi = \pi + \arctg \left( \dfrac{2}{3} \right)$, $\arg z = \pi + \arctg \left( \dfrac{2}{3} \right)$"
        kn=r"$\varphi = \arctg \left( \dfrac{2}{3} \right) - \pi$, $\arg z = \arctg \left( \dfrac{2}{3} \right) - \pi$"
        assert k.count(ko)==1; kw["k"]=k.replace(ko,kn)
        why+="; в ключе е) стоял $\\pi+\\arctg\\frac{2}{3}\\approx3{,}73>\\pi$ (вне промежутка, в отличие от пунктов б)–г)); для $-3-2i$ (III четверть) главный аргумент $\\arctg\\frac{2}{3}-\\pi$"
        kw["dnew"]={2:(r"е) $z = \sqrt{13}(\cos \varphi + i \sin \varphi)$, $\varphi = \arctg\left(\dfrac{2}{3}\right)$, $\arg z = \arctg\left(\dfrac{2}{3}\right)$",
                       r"Ученик не учёл, что число $-3-2i$ лежит в третьей четверти, и взял $\arctg\dfrac{2}{3}$ — угол первой четверти; для третьей четверти из него нужно вычесть $\pi$: $\arg z=\arctg\dfrac{2}{3}-\pi$.")}
    o.append("E(%r, r%r,\n  %s)\n"%(t,why,",\n  ".join("%s=%s"%(a,("r%r"%b) if isinstance(b,str) else "{"+", ".join("%d: (r%r, r%r)"%(i,v,w) for i,(v,w) in b.items())+"}") for a,b in kw.items())))
open("specs/fix_ctrl130.py","w").write("\n".join(o).replace("\\\\","\\"))
