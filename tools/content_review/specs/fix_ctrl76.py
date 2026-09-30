# -*- coding: utf-8 -*-
S = "полный обзор задач 11 класса (очередь G9–G11), проверено вычислением"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G11_TB_§3_86_в", r"условие было текстом доказательства (без вопроса), а дистракторы — варианты формулы; сформулирован вопрос: $\operatorname{ctg}(\arcsin x)=\frac{\cos\alpha}{\sin\alpha}=\frac{\sqrt{1-x^{2}}}{x}$ при $\alpha=\arcsin x\in[-\frac\pi2;\frac\pi2]$ ($\cos\alpha\ge0$)",
  q=r"Выразите $\operatorname{ctg}(\arcsin x)$ через $x$ для $x\in[-1;0)\cup(0;1]$.",
  k=r"$\dfrac{\sqrt{1-x^{2}}}{x}$")
E("G11_TB_§3_86_пример", r"в условии было приведено всё решение с ответом «$=0$»; оставлен вопрос. Проверка: $\cos(\alpha+\beta)=\frac{16}{65}$, $\sin(\alpha+\beta)=\frac{63}{65}$, $\cos(\alpha+\beta+\gamma)=\frac{16}{65}\cdot\frac{63}{65}-\frac{63}{65}\cdot\frac{16}{65}=0$ (сумма равна $\frac\pi2$). Дистракторы переписаны (старые содержали неверные вычисления)",
  q=r"Вычислите $\cos\left(\arcsin\dfrac{4}{5}+\arcsin\dfrac{5}{13}+\arcsin\dfrac{16}{65}\right)$.",
  dnew={0: (r"$\dfrac{16}{65}$", r"Ученик вычислил только $\cos(\alpha+\beta)=\frac35\cdot\frac{12}{13}-\frac45\cdot\frac5{13}=\frac{16}{65}$ и не учёл третье слагаемое $\gamma$: $\cos(\alpha+\beta+\gamma)=\cos(\alpha+\beta)\cos\gamma-\sin(\alpha+\beta)\sin\gamma=0$."),
        1: (r"$\dfrac{56}{65}$", r"Ученик записал косинус суммы с плюсом: $\cos(\alpha+\beta)=\cos\alpha\cos\beta+\sin\alpha\sin\beta=\frac{36}{65}+\frac{20}{65}=\frac{56}{65}$; верно $\cos(\alpha+\beta)=\cos\alpha\cos\beta-\sin\alpha\sin\beta=\frac{16}{65}$."),
        2: (r"$\dfrac{63}{65}$", r"Ученик нашёл только $\cos\gamma=\sqrt{1-\left(\frac{16}{65}\right)^{2}}=\frac{63}{65}$ и принял это за ответ; надо было вычислить косинус суммы трёх углов.")})
