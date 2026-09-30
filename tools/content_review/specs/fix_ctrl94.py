# -*- coding: utf-8 -*-
S = "полный обзор задач 9 класса (очередь G9–G11), условие сверено с текстом учебника (№246.6), знаки проверены по четвертям"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G9_TB_20_246_6", r"$1{,}5\pi<\alpha\le1{,}8\pi$ — угол в IV четверти ($270^{\circ}<\alpha\le324^{\circ}$): $\sin<0$, $\cos>0$, $\operatorname{tg}<0$, $\operatorname{ctg}<0$; в ключе стоял $\cos<0$ (это III четверть)",
  k=r"$\sin: -,\ \cos: +,\ \operatorname{tg}: -,\ \operatorname{ctg}: -$",
  dnew={0: (r"$\sin: -,\ \cos: -,\ \operatorname{tg}: -,\ \operatorname{ctg}: -$", r"Ученик верно определил, что синус отрицателен, но косинус взял отрицательным (как в III четверти); в IV четверти абсцисса точки положительна, поэтому $\cos\alpha>0$."),
        1: (r"$\sin: +,\ \cos: +,\ \operatorname{tg}: +,\ \operatorname{ctg}: +$", r"Ученик отнёс угол к I четверти, не заметив, что $1{,}5\pi<\alpha\le1{,}8\pi$ — это четвёртая четверть (между $270^{\circ}$ и $360^{\circ}$)."),
        2: (r"$\sin: -,\ \cos: -,\ \operatorname{tg}: +,\ \operatorname{ctg}: +$", r"Ученик отнёс угол к III четверти, где тангенс и котангенс положительны; но угол лежит в IV четверти, где $\operatorname{tg}\alpha<0$ и $\operatorname{ctg}\alpha<0$.")})
