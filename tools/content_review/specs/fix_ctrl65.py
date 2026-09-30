# -*- coding: utf-8 -*-
S = "полный обзор задач 11 класса (очередь G9–G11), проверено вычислением"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G11_TB_?_237_a", r"$A=\cos x\ge0$, $B=\sin y$: $A^{2}+B^{2}=\frac54$, $AB=\frac{\sqrt6}{4}>0$, то есть $(A^{2},B^{2})=(\frac34,\frac12)$ или $(\frac12,\frac34)$; ключ содержал только первую пару значений, вторая ($\cos x=\frac{\sqrt2}{2}$, $\sin y=\frac{\sqrt3}{2}$) была потеряна",
  k=r"$x = \pm\dfrac{\pi}{6} + 2\pi n$, $y = \dfrac{\pi}{4} + 2\pi k$ или $y = \dfrac{3\pi}{4} + 2\pi k$; $x = \pm\dfrac{\pi}{4} + 2\pi n$, $y = \dfrac{\pi}{3} + 2\pi k$ или $y = \dfrac{2\pi}{3} + 2\pi k$, $n,k \in \mathbb{Z}$",
  dnew={2: (r"$x = \pm\dfrac{\pi}{6} + 2\pi n$, $y = \dfrac{\pi}{4} + 2\pi k$ или $y = \dfrac{3\pi}{4} + 2\pi k$, $n,k \in \mathbb{Z}$", r"Ученик разобрал только случай $\cos^{2}x=\frac34$, $\sin^{2}y=\frac12$ и потерял вторую пару значений $\cos^{2}x=\frac12$, $\sin^{2}y=\frac34$.")})
E("G11_TB_?_237_b", r"$A=\sin x$, $B=\cos y$: $A^{2}+B^{2}=\frac32$, $AB=\frac34$, откуда $A=B=\pm\frac{\sqrt3}{2}$; при $\cos y=-\frac{\sqrt3}{2}$ решения $y=\pm\frac{5\pi}{6}+2\pi n$; в ключе было только $y=-\frac{5\pi}{6}+2\pi n$",
  k=r"$x = (-1)^{k} \cdot \dfrac{\pi}{3} + \pi k$, $y = \pm \dfrac{\pi}{6} + 2\pi n$; $x = (-1)^{k+1} \cdot \dfrac{\pi}{3} + \pi k$, $y = \pm\dfrac{5\pi}{6} + 2\pi n$, $k, n \in \mathbb{Z}$",
  dnew={0: (r"$x = (-1)^{k} \cdot \dfrac{\pi}{3} + \pi k$, $y = \pm \dfrac{\pi}{6} + 2\pi n$; $x = (-1)^{k+1} \cdot \dfrac{\pi}{3} + \pi k$, $y = -\dfrac{5\pi}{6} + 2\pi n$, $k, n \in \mathbb{Z}$", r"Ученик для $\sin x=-\frac{\sqrt3}{2}$, $\cos y=-\frac{\sqrt3}{2}$ записал только $y=-\frac{5\pi}{6}+2\pi n$ и потерял $y=\frac{5\pi}{6}+2\pi n$.")})
