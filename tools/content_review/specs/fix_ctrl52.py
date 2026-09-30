# -*- coding: utf-8 -*-
S = "полный обзор задач 11 класса (очередь G9–G11), проверено вычислением по формуле Муавра"
P = {}
def E(t, why, **kw): P[t] = dict(src=S, why=why, **kw)
E("G11_TB_17_2*_17_15_c", r"$z=e^{i5\pi/6}$, $z^{6}=-1$, $z^{7}=-z=\frac{\sqrt3}{2}-\frac{i}{2}$; в ключе седьмая степень была $-\frac{\sqrt3}{2}-\frac{i}{2}$",
  k=r"$- \dfrac{\sqrt{3}}{2} + \dfrac{i}{2}, \dfrac{1}{2} - i \dfrac{\sqrt{3}}{2}, i, -\dfrac{1}{2} - i \dfrac{\sqrt{3}}{2}, \dfrac{\sqrt{3}}{2} + \dfrac{i}{2}, -1, \dfrac{\sqrt{3}}{2} - \dfrac{i}{2}$")
E("G11_TB_17_2*_17_15_d", r"$z=e^{i7\pi/6}$, $z^{6}=-1$, $z^{7}=-z=\frac{\sqrt3}{2}+\frac{i}{2}$; в ключе седьмая степень была $-\frac{\sqrt3}{2}+\frac{i}{2}$",
  k=r"$- \dfrac{\sqrt{3}}{2} - \dfrac{i}{2}, \dfrac{1}{2} + i \dfrac{\sqrt{3}}{2}, -i, \dfrac{-1}{2} + i \dfrac{\sqrt{3}}{2}, \dfrac{\sqrt{3}}{2} - \dfrac{i}{2}, -1, \dfrac{\sqrt{3}}{2} + \dfrac{i}{2}$")
