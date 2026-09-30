# -*- coding: utf-8 -*-
S = "сплошной скан равенства вариантов и ключа (с греческими буквами); проверено вычислением"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G9_TB_26_314_1", "числитель $\\cos\\alpha+\\sin\\alpha$, знаменатель $-\\cos\\alpha-\\sin\\alpha$: дробь равна $-1$; ключ был записан несокращённой дробью",
  k="$-1$")
E("G9_TB_26_314_2", "числитель $-\\cos\\alpha+\\sin\\alpha$ равен знаменателю $\\sin\\alpha-\\cos\\alpha$, значение $1$; ключ был записан дробью, а вариант «$1$» с неверным пояснением совпадал с верным ответом",
  k="$1$",
  dnew={0: (r"$\dfrac{\sin\alpha+\cos\alpha}{\sin\alpha-\cos\alpha}$", "Ученик принял $\\cos(\\pi-\\alpha)=\\cos\\alpha$ (потерял знак «−»): числитель стал $\\sin\\alpha+\\cos\\alpha$, дробь не сократилась.")})
E("G9_TB_26_314_3", "в условии дроби были разорваны при распознавании; восстановлено $\\frac{\\sin(\\alpha-\\pi)}{\\operatorname{tg}(\\alpha+\\pi)}\\cdot\\frac{\\operatorname{tg}(\\pi-\\alpha)}{\\cos(\\frac{\\pi}{2}-\\alpha)}=(-\\cos\\alpha)\\cdot(-\\frac1{\\cos\\alpha})=1$, что подтверждает ключ",
  q=r"Упростите выражение: $\dfrac{\sin(\alpha-\pi)}{\operatorname{tg}(\alpha+\pi)} \cdot \dfrac{\operatorname{tg}(\pi-\alpha)}{\cos\left(\dfrac{\pi}{2}-\alpha\right)}$")
E("G9_TB_ПовтКурс_547_1", "неверный вариант $\\sin\\alpha(2\\cos\\alpha-2)$ тождественно равен ключу (вынесен не весь общий множитель); заменён на потерю множителя $2$",
  dnew={1: (r"$\sin{\alpha}(\cos{\alpha} - 1)$", "Ученик вынес за скобки только $\\sin\\alpha$ и потерял множитель $2$ в записи ответа.")})
E("G10_TB_§21_21_3_9", "неверный вариант $\\cos\\alpha\\cos\\beta+\\sin\\alpha\\sin\\beta$ равен $\\cos(\\alpha-\\beta)$, то есть ключу; заменён на реальную ошибку",
  dnew={1: (r"$\cos{\alpha} \cos{\beta} + 3\sin{\alpha} \sin{\beta}$", "Ученик разложил $\\cos(\\alpha+\\beta)$ как $\\cos\\alpha\\cos\\beta+\\sin\\alpha\\sin\\beta$ (знак «−» потерян) и прибавил $2\\sin\\alpha\\sin\\beta$.")})
