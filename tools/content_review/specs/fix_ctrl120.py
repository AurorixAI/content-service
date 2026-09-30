# -*- coding: utf-8 -*-
S = "полный обзор задач 9 класса (очередь G9–G11), проверено вычислением"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G9_TB_ПовтКурс_546_1", r"$\cos\alpha=0{,}8$, $\cos\beta=-0{,}96$; $\cos(\alpha-\beta)=\cos\alpha\cos\beta+\sin\alpha\sin\beta=-0{,}768-0{,}168=-0{,}936$. В ключе $-0{,}8$ — значение $\sin(\alpha+\beta)$ из соседней задачи",
  k=r"$-0{,}936$",
  dnew={0: (r"$-0{,}6$", r"Ученик применил формулу косинуса суммы: $\cos\alpha\cos\beta-\sin\alpha\sin\beta=-0{,}6$, а нужен косинус разности."),
        1: (r"$-0{,}8$", r"Ученик вычислил $\sin(\alpha+\beta)=\sin\alpha\cos\beta+\cos\alpha\sin\beta=-0{,}8$ вместо $\cos(\alpha-\beta)$."),
        2: (r"$0{,}6$", r"Ученик взял $\cos\beta=+0{,}96$, не учтя, что $\pi<\beta<\frac{3\pi}2$ — угол третьей четверти, где косинус отрицателен.")})
E("G9_TB_ПовтКурс_548_1", r"$\sin\frac\alpha2=-\frac{15}{17}$; $\sin\alpha=2\sin\frac\alpha2\cos\frac\alpha2=2\cdot\left(-\frac{15}{17}\right)\left(-\frac8{17}\right)=\frac{240}{289}$ (произведение двух отрицательных положительно); $\cos\alpha=2\cos^{2}\frac\alpha2-1=\frac{128}{289}-1=-\frac{161}{289}$. В ключе знак $\sin\alpha$ был отрицательным",
  k=r"$\sin\alpha = \dfrac{240}{289}$, $\cos\alpha = -\dfrac{161}{289}$",
  dnew={0: (r"$\sin\alpha = -\dfrac{240}{289}$, $\cos\alpha = -\dfrac{161}{289}$", r"Ученик верно нашёл $\sin\frac\alpha2=-\frac{15}{17}$ и $\cos\alpha$, но при вычислении $2\sin\frac\alpha2\cos\frac\alpha2$ забыл, что произведение двух отрицательных чисел положительно.")})
