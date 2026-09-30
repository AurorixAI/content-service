# -*- coding: utf-8 -*-
S = "полный обзор задач 10 класса (очередь G9–G11), проверено вычислением"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G10_TB_§1_1_42_1", "$\\sqrt{x}\\ge0$, значит $f(x)=\\sqrt{x}+2\\ge2$: область значений $[2;+\\infty)$ (в ключе стояло $[0;+\\infty)$)", k=r"$[2; +\infty)$")
E("G10_TB_§23_23_1_8", "в ключе формула тангенса двойного угла была искажена лишним множителем $5$ и точкой: $\\operatorname{tg}3=\\frac{2\\operatorname{tg}1{,}5}{1-\\operatorname{tg}^21{,}5}$",
  k=r"$\dfrac{2 \tg{1{,}5}}{1 - \tg^{2}{1{,}5}}$")
E("G10_TB_§23_23_4_10", "в условии дробь $\\frac{2\\operatorname{tg}1{,}5\\alpha}{1+\\operatorname{tg}^2 1{,}5\\alpha}$ была разорвана запятой, числитель «$2\\operatorname{tg}$» стал отдельным выражением, а «$2$» в числителе — «$5$»; ключ $\\sin3\\alpha$ подтверждает",
  q=r"Упростите выражение: $\dfrac{2\operatorname{tg}1{,}5\alpha}{1+\operatorname{tg}^{2}1{,}5\alpha}$")
E("G10_TB_§20_20_2_8", "в конце условия остался лишний символ «$\\operatorname{tg}$» после выражения; ключ $4$ верен для $(\\operatorname{tg}\\beta+\\operatorname{ctg}\\beta)^2-(\\operatorname{tg}\\beta-\\operatorname{ctg}\\beta)^2$",
  q=r"Упростите выражение: 8) $(\tg \beta + \ctg \beta)^{2} - (\tg \beta - \ctg \beta)^{2}$")
