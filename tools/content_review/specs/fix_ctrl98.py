# -*- coding: utf-8 -*-
S = "полный обзор задач 9 класса (очередь G9–G11), проверено вычислением"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G9_TB_24_281_3", r"$\cos A\cos B-\sin A\sin B=\cos(A+B)=\cos\left(\frac{7\pi}{9}+\frac{11\pi}{9}\right)=\cos2\pi=1$ (ключ был $-1$; верный ответ $1$ стоял среди дистракторов)",
  k=r"$1$",
  dnew={0: (r"$-1$", r"Ученик верно применил формулу косинуса суммы и получил $\cos 2\pi$, но принял значение $\cos2\pi$ за $-1$ (перепутал с $\cos\pi$)."),
        1: (r"$0$", r"Ученик верно нашёл $\cos(A+B)=\cos2\pi$, но перепутал табличное значение: $\cos 2\pi=1$, а не $0$."),
        2: (r"$\cos\dfrac{4\pi}{9}$", r"Ученик применил формулу косинуса разности $\cos(A-B)$ вместо косинуса суммы: $\frac{11\pi}{9}-\frac{7\pi}{9}=\frac{4\pi}{9}$.")})
E("G9_TB_24_282_1", r"$\cos\alpha=\sqrt{1-\frac13}=\sqrt{\frac23}$; $\cos\left(\frac\pi3+\alpha\right)=\frac12\sqrt{\frac23}-\frac{\sqrt3}{2}\cdot\frac1{\sqrt3}=\frac{\sqrt2}{2\sqrt3}-\frac12=\frac{\sqrt2-\sqrt3}{2\sqrt3}$ (числено $-0{,}092$); в ключе стояло $\frac{\sqrt2-1}{2\sqrt3}\approx0{,}120$",
  k=r"$\dfrac{\sqrt{2}-\sqrt{3}}{2\sqrt{3}}$",
  dnew={0: (r"$\dfrac{\sqrt{2}-1}{2\sqrt{3}}$", r"Ученик верно нашёл $\cos\alpha$, но произведение $\frac{\sqrt3}{2}\cdot\frac1{\sqrt3}$ вычислил как $\frac{1}{2\sqrt3}$ вместо $\frac12$."),
        1: (r"$\dfrac{\sqrt{2}+\sqrt{3}}{2\sqrt{3}}$", r"Ученик верно нашёл оба слагаемых, но поставил между ними знак «плюс»; в формуле косинуса суммы $\cos(\frac\pi3+\alpha)=\cos\frac\pi3\cos\alpha-\sin\frac\pi3\sin\alpha$ стоит «минус»."),
        },
  dadd=[(r"$\dfrac{\sqrt{2}}{2\sqrt{3}}+\dfrac{1}{2}$", r"Ученик записал $\cos(\alpha+\beta)=\cos\alpha\cos\beta+\sin\alpha\sin\beta$ (формула косинуса разности) и получил сумму вместо разности.")])
