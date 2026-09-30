# -*- coding: utf-8 -*-
S = "полный обзор задач 9 класса (очередь G9–G11), проверено вычислением по знакам синуса и косинуса"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G9_TB_21_253_4", r"$\cos\alpha-\sin\alpha=1{,}2>1$: в I четверти $\cos\alpha-\sin\alpha<\cos\alpha\le1$; во II $\cos\alpha<0<\sin\alpha$, разность отрицательна; в III разность $|\sin\alpha|-|\cos\alpha|\le1$; значение $1{,}2$ возможно только при $\cos\alpha>0>\sin\alpha$ — IV четверть (например, $\alpha\approx-13^{\circ}$). Ключ «II» противоречил условию (в II четверти $\cos\alpha-\sin\alpha<0$)",
  k=r"$IV$ четверть",
  dnew={0: (r"$I$ четверть", r"Ученик решил, что положительная разность $\cos\alpha-\sin\alpha$ выполняется в первой четверти; но там $\cos\alpha-\sin\alpha<\cos\alpha\le1<1{,}2$."),
        1: (r"$II$ четверть", r"Ученик перепутал знаки в разности: во II четверти $\cos\alpha<0$, $\sin\alpha>0$, поэтому $\cos\alpha-\sin\alpha<0$, а не $1{,}2$."),
        2: (r"$III$ четверть", r"Ученик решил, что при отрицательных синусе и косинусе разность может быть большой; но в III четверти $\cos\alpha-\sin\alpha=|\sin\alpha|-|\cos\alpha|\le1<1{,}2$.")})
