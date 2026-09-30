# -*- coding: utf-8 -*-
# Новые задачи: тригонометрия 9 класса (навыки с < 3 подходящими задачами), 26.09.
from sympy import *
import random
al, be, x = symbols("alpha beta x")
R = Rational
G = []
def T(skill, diff, atype, q, k, ds, check, vals=None):
    G.append(dict(skill=skill, diff=diff, atype=atype, q=q, k=k, ds=ds, check=check, vals=vals))
def same(e1, e2, sym=(al, be, x)):
    """numeric identity check at random points (for trig expressions)"""
    rnd = random.Random(7)
    for _ in range(6):
        p = {s: R(rnd.randint(1, 40), 37) for s in sym}
        if abs(complex(N((e1 - e2).subs(p)))) > 1e-9: return False
    return True
deg = lambda d: d * pi / 180

# S17_03 перевод в радианы
T("G9_S17_03", "A", "expression", r"Выразите в радианах угол $60^{\circ}$.", r"$\dfrac{\pi}{3}$",
  [(r"$\dfrac{\pi}{6}$", "Ученик перепутал 60° с 30°."), (r"$3\pi$", "Ученик разделил 180 на 60 вместо того, чтобы умножить 60 на π/180."),
   (r"$\dfrac{60}{\pi}$", "Ученик разделил градусную меру на π, а не умножил на π/180.")],
  lambda: 60 * pi / 180 == pi / 3, vals=[pi / 3, pi / 6, 3 * pi, 60 / pi])
T("G9_S17_03", "B", "expression", r"Выразите в радианах угол $150^{\circ}$.", r"$\dfrac{5\pi}{6}$",
  [(r"$\dfrac{6\pi}{5}$", "Ученик перевернул дробь 150/180."), (r"$\dfrac{5\pi}{3}$", "Ученик разделил 150 на 90, а не на 180."),
   (r"$\dfrac{3\pi}{4}$", "Ученик перепутал 150° со 135°.")],
  lambda: 150 * pi / 180 == 5 * pi / 6, vals=[5 * pi / 6, 6 * pi / 5, 5 * pi / 3, 3 * pi / 4])
# S20_05 четверть по знакам
T("G9_S20_05", "A", "text", r"В какой координатной четверти лежит угол $\alpha$, если $\sin\alpha > 0$ и $\cos\alpha < 0$?", "во II четверти",
  [("в I четверти", "Ученик учёл только условие sin α > 0."), ("в III четверти", "Ученик перепутал знаки синуса: в III четверти sin α < 0."),
   ("в IV четверти", "Ученик перепутал синус с косинусом.")],
  lambda: sin(2 * pi / 3) > 0 and cos(2 * pi / 3) < 0)
T("G9_S20_05", "B", "text", r"В какой координатной четверти лежит угол $\alpha$, если $\operatorname{tg}\alpha > 0$ и $\sin\alpha < 0$?", "в III четверти",
  [("в I четверти", "Ученик учёл только условие tg α > 0."), ("во II четверти", "Ученик считал, что во II четверти тангенс положителен."),
   ("в IV четверти", "Ученик учёл только условие sin α < 0 и выбрал не ту четверть: в IV четверти tg α < 0.")],
  lambda: tan(4 * pi / 3) > 0 and sin(4 * pi / 3) < 0)
# S21_03 tg·ctg
T("G9_S21_03", "A", "exact_number", r"Вычислите $\operatorname{tg}\alpha \cdot \operatorname{ctg}\alpha$ при $\alpha \neq \dfrac{\pi k}{2}$, $k \in \mathbb{Z}$.", r"$1$",
  [(r"$0$", "Ученик решил, что тангенс и котангенс взаимно уничтожаются, а они взаимно обратны."),
   (r"$-1$", "Ученик ошибся в знаке: tg α и ctg α одного знака."),
   (r"$\operatorname{tg}^{2}\alpha$", "Ученик заменил ctg α на tg α.")],
  lambda: same(tan(al) * cot(al), Integer(1)))
T("G9_S21_03", "B", "exact_number", r"Упростите выражение $3\operatorname{tg}\alpha \cdot \operatorname{ctg}\alpha - 1$.", r"$2$",
  [(r"$3\operatorname{tg}^{2}\alpha - 1$", "Ученик заменил ctg α на tg α."), (r"$-2$", "Ученик считал, что tg α · ctg α = −1."),
   (r"$4$", "Ученик прибавил 1 вместо вычитания.")],
  lambda: same(3 * tan(al) * cot(al) - 1, Integer(2)))
# S21_05 1 + ctg²
T("G9_S21_05", "A", "exact_number", r"Найдите $\sin^{2}\alpha$, если $\operatorname{ctg}\alpha = 3$.", r"$\dfrac{1}{10}$",
  [(r"$\dfrac{1}{9}$", "Ученик взял 1/ctg²α, забыв, что 1 + ctg²α = 1/sin²α."), (r"$\dfrac{9}{10}$", "Ученик нашёл cos²α вместо sin²α."),
   (r"$10$", "Ученик нашёл 1/sin²α и не перевернул дробь.")],
  lambda: 1 / (1 + Integer(3)**2) == R(1, 10), vals=[R(1, 10), R(1, 9), R(9, 10), 10])
T("G9_S21_05", "B", "expression", r"Найдите $\sin\alpha$, если $\operatorname{ctg}\alpha = 3$ и $0 < \alpha < \dfrac{\pi}{2}$.", r"$\dfrac{\sqrt{10}}{10}$",
  [(r"$-\dfrac{\sqrt{10}}{10}$", "Ученик выбрал неверный знак: в I четверти sin α > 0."), (r"$\dfrac{1}{3}$", "Ученик перепутал sin α с tg α = 1/ctg α."),
   (r"$\dfrac{3\sqrt{10}}{10}$", "Ученик нашёл cos α вместо sin α.")],
  lambda: sin(acot(3)) == sqrt(10) / 10, vals=[sqrt(10) / 10, -sqrt(10) / 10, R(1, 3), 3 * sqrt(10) / 10])
# S22_07 вычисление через тождество
T("G9_S22_07", "B", "exact_number", r"Вычислите $\sin^{2}\alpha + \sin^{2}\alpha \cdot \operatorname{tg}^{2}\alpha$, если $\cos\alpha = \dfrac{1}{3}$.", r"$8$",
  [(r"$\dfrac{8}{9}$", "Ученик нашёл только sin²α и остановился."), (r"$\dfrac{1}{8}$", "Ученик перевернул дробь: tg²α = sin²α/cos²α = 8, а не 1/8."),
   (r"$9$", "Ученик нашёл 1/cos²α вместо tg²α.")],
  lambda: (1 - R(1, 9)) * (1 + (1 - R(1, 9)) / R(1, 9)) == 8, vals=[8, R(8, 9), R(1, 8), 9])
T("G9_S22_07", "A", "exact_number", r"Найдите значение выражения $(1 - \cos^{2}\alpha)(1 + \operatorname{ctg}^{2}\alpha)$ при $\sin\alpha \neq 0$.", r"$1$",
  [(r"$0$", "Ученик решил, что 1 − cos²α = 0."), (r"$2$", "Ученик сложил единицы из скобок вместо применения тождеств."),
   (r"$\sin^{2}\alpha$", "Ученик упростил только первую скобку.")],
  lambda: same((1 - cos(al)**2) * (1 + cot(al)**2), Integer(1)))
# S23_01 синус отрицательного угла
T("G9_S23_01", "A", "exact_number", r"Найдите $\sin(-30^{\circ})$.", r"$-\dfrac{1}{2}$",
  [(r"$\dfrac{1}{2}$", "Ученик считал синус чётной функцией: sin(−α) = −sin α."), (r"$-\dfrac{\sqrt{3}}{2}$", "Ученик перепутал sin 30° и cos 30°."),
   (r"$\dfrac{\sqrt{3}}{2}$", "Ученик перепутал sin 30° и cos 30° и потерял знак.")],
  lambda: sin(deg(-30)) == -R(1, 2), vals=[-R(1, 2), R(1, 2), -sqrt(3) / 2, sqrt(3) / 2])
T("G9_S23_01", "B", "exact_number", r"Вычислите $2\sin\left(-\dfrac{\pi}{6}\right) + \sin\dfrac{\pi}{2}$.", r"$0$",
  [(r"$2$", "Ученик считал, что sin(−π/6) = sin(π/6)."), (r"$-2$", "Ученик ошибся в значении sin(π/2), взяв −1."),
   (r"$1$", "Ученик потерял множитель 2 перед синусом.")],
  lambda: 2 * sin(-pi / 6) + sin(pi / 2) == 0)
# S23_02 косинус отрицательного угла
T("G9_S23_02", "A", "exact_number", r"Найдите $\cos(-60^{\circ})$.", r"$\dfrac{1}{2}$",
  [(r"$-\dfrac{1}{2}$", "Ученик считал косинус нечётной функцией, а cos(−α) = cos α."), (r"$\dfrac{\sqrt{3}}{2}$", "Ученик перепутал cos 60° и sin 60°."),
   (r"$-\dfrac{\sqrt{3}}{2}$", "Ученик перепутал cos 60° и sin 60° и поставил лишний минус.")],
  lambda: cos(deg(-60)) == R(1, 2), vals=[R(1, 2), -R(1, 2), sqrt(3) / 2, -sqrt(3) / 2])
T("G9_S23_02", "B", "exact_number", r"Вычислите $\cos\left(-\dfrac{\pi}{4}\right) \cdot \cos\dfrac{\pi}{4}$.", r"$\dfrac{1}{2}$",
  [(r"$-\dfrac{1}{2}$", "Ученик считал, что cos(−π/4) = −cos(π/4)."), (r"$\dfrac{\sqrt{2}}{2}$", "Ученик не перемножил множители, а взял значение одного из них."),
   (r"$1$", "Ученик считал, что cos(π/4) = 1.")],
  lambda: cos(-pi / 4) * cos(pi / 4) == R(1, 2), vals=[R(1, 2), -R(1, 2), sqrt(2) / 2, 1])
# S26_05 приведение π/2 − α
T("G9_S26_05", "A", "expression", r"Упростите $\cos\left(\dfrac{\pi}{2} - \alpha\right)$.", r"$\sin\alpha$",
  [(r"$\cos\alpha$", "Ученик не сменил функцию на кофункцию при угле π/2."), (r"$-\sin\alpha$", "Ученик поставил лишний минус: угол π/2 − α лежит в I четверти."),
   (r"$-\cos\alpha$", "Ученик не сменил функцию и поставил лишний минус.")],
  lambda: same(cos(pi / 2 - al), sin(al)), vals=[sin(al), cos(al), -sin(al), -cos(al)])
T("G9_S26_05", "B", "expression", r"Упростите $\sin\left(\dfrac{\pi}{2} - \alpha\right) - \cos\alpha$.", r"$0$",
  [(r"$2\cos\alpha$", "Ученик заменил sin(π/2 − α) на −cos α."), (r"$\sin\alpha - \cos\alpha$", "Ученик не сменил функцию на кофункцию."),
   (r"$-2\cos\alpha$", "Ученик ошибся в знаке и получил −cos α − cos α.")],
  lambda: same(sin(pi / 2 - al) - cos(al), Integer(0)), vals=[Integer(0), 2 * cos(al), sin(al) - cos(al), -2 * cos(al)])
# S26_06 приведение отрицательного угла
T("G9_S26_06", "A", "exact_number", r"Найдите $\cos\left(-\dfrac{\pi}{3}\right)$.", r"$\dfrac{1}{2}$",
  [(r"$-\dfrac{1}{2}$", "Ученик вынес минус из-под косинуса, хотя косинус — чётная функция."), (r"$\dfrac{\sqrt{3}}{2}$", "Ученик перепутал cos(π/3) и sin(π/3)."),
   (r"$-\dfrac{\sqrt{3}}{2}$", "Ученик перепутал cos(π/3) и sin(π/3) и вынес минус.")],
  lambda: cos(-pi / 3) == R(1, 2), vals=[R(1, 2), -R(1, 2), sqrt(3) / 2, -sqrt(3) / 2])
T("G9_S26_06", "B", "exact_number", r"Вычислите $\operatorname{tg}\left(-\dfrac{\pi}{4}\right) \cdot \operatorname{ctg}\left(-\dfrac{\pi}{3}\right)$.", r"$\dfrac{\sqrt{3}}{3}$",
  [(r"$-\dfrac{\sqrt{3}}{3}$", "Ученик вынес минус только из одного множителя, хотя tg и ctg — нечётные функции."), (r"$\sqrt{3}$", "Ученик взял tg(π/3) вместо ctg(π/3)."),
   (r"$-\sqrt{3}$", "Ученик взял tg(π/3) вместо ctg(π/3) и потерял один из минусов.")],
  lambda: simplify(tan(-pi / 4) * cot(-pi / 3) - sqrt(3) / 3) == 0, vals=[sqrt(3) / 3, -sqrt(3) / 3, sqrt(3), -sqrt(3)])
# S26_11 произведения
T("G9_S26_11", "B", "expression", r"Упростите $\sin\left(\dfrac{\pi}{2} - \alpha\right) \cdot \operatorname{tg}(\pi - \alpha)$.", r"$-\sin\alpha$",
  [(r"$\sin\alpha$", "Ученик не учёл, что tg(π − α) = −tg α."), (r"$-\cos\alpha$", "Ученик заменил sin(π/2 − α) на sin α и неверно сократил."),
   (r"$-\operatorname{tg}\alpha$", "Ученик потерял множитель cos α = sin(π/2 − α).")],
  lambda: same(sin(pi / 2 - al) * tan(pi - al), -sin(al)), vals=[-sin(al), sin(al), -cos(al), -tan(al)])
T("G9_S26_11", "B", "expression", r"Упростите $\cos(\pi + \alpha) \cdot \sin\left(\dfrac{\pi}{2} + \alpha\right)$.", r"$-\cos^{2}\alpha$",
  [(r"$\cos^{2}\alpha$", "Ученик не учёл, что cos(π + α) = −cos α."), (r"$-\sin\alpha\cos\alpha$", "Ученик не сменил функцию во втором множителе: sin(π/2 + α) = cos α."),
   (r"$-\sin^{2}\alpha$", "Ученик сменил функцию в обоих множителях.")],
  lambda: same(cos(pi + al) * sin(pi / 2 + al), -cos(al)**2), vals=[-cos(al)**2, cos(al)**2, -sin(al) * cos(al), -sin(al)**2])
# S26_14 tg и ctg
T("G9_S26_14", "A", "expression", r"Упростите $\operatorname{tg}(\pi - \alpha) + \operatorname{ctg}\left(\dfrac{\pi}{2} - \alpha\right)$.", r"$0$",
  [(r"$2\operatorname{tg}\alpha$", "Ученик не учёл, что tg(π − α) = −tg α."), (r"$-2\operatorname{tg}\alpha$", "Ученик считал, что ctg(π/2 − α) = −tg α."),
   (r"$\operatorname{tg}\alpha + \operatorname{ctg}\alpha$", "Ученик не сменил функцию во втором слагаемом и не учёл знак в первом.")],
  lambda: same(tan(pi - al) + cot(pi / 2 - al), Integer(0)), vals=[Integer(0), 2 * tan(al), -2 * tan(al), tan(al) + cot(al)])
T("G9_S26_14", "B", "expression", r"Упростите $\operatorname{tg}(\pi + \alpha) \cdot \operatorname{ctg}\left(\dfrac{3\pi}{2} - \alpha\right)$.", r"$\operatorname{tg}^{2}\alpha$",
  [(r"$-\operatorname{tg}^{2}\alpha$", "Ученик ошибся в знаке: угол 3π/2 − α лежит в III четверти, где котангенс положителен."),
   (r"$1$", "Ученик не сменил функцию во втором множителе и получил tg α · ctg α."), (r"$-1$", "Ученик не сменил функцию и ошибся в знаке.")],
  lambda: same(tan(pi + al) * cot(3 * pi / 2 - al), tan(al)**2), vals=[tan(al)**2, -tan(al)**2, Integer(1), Integer(-1)])
# S27_08 сумма синусов → произведение
T("G9_S27_08", "A", "expression", r"Представьте в виде произведения $\sin 3\alpha + \sin\alpha$.", r"$2\sin 2\alpha\cos\alpha$",
  [(r"$2\cos 2\alpha\sin\alpha$", "Ученик поменял местами синус и косинус в формуле суммы синусов."), (r"$\sin 4\alpha$", "Ученик сложил аргументы синусов."),
   (r"$2\sin 4\alpha\cos 2\alpha$", "Ученик не разделил полусумму и полуразность аргументов на 2.")],
  lambda: same(sin(3 * al) + sin(al), 2 * sin(2 * al) * cos(al)), vals=[2 * sin(2 * al) * cos(al), 2 * cos(2 * al) * sin(al), sin(4 * al), 2 * sin(4 * al) * cos(2 * al)])
T("G9_S27_08", "B", "expression", r"Представьте в виде произведения $\sin 5x + \sin 3x$.", r"$2\sin 4x\cos x$",
  [(r"$2\cos 4x\sin x$", "Ученик поменял местами синус и косинус в формуле суммы синусов."), (r"$2\sin 8x\cos 2x$", "Ученик не разделил сумму и разность аргументов на 2."),
   (r"$\sin 8x$", "Ученик сложил аргументы синусов.")],
  lambda: same(sin(5 * x) + sin(3 * x), 2 * sin(4 * x) * cos(x)), vals=[2 * sin(4 * x) * cos(x), 2 * cos(4 * x) * sin(x), 2 * sin(8 * x) * cos(2 * x), sin(8 * x)])
# S27_09 сумма косинусов → произведение
T("G9_S27_09", "A", "expression", r"Представьте в виде произведения $\cos 5\alpha + \cos 3\alpha$.", r"$2\cos 4\alpha\cos\alpha$",
  [(r"$-2\sin 4\alpha\sin\alpha$", "Ученик применил формулу разности косинусов вместо суммы."), (r"$2\cos 8\alpha\cos 2\alpha$", "Ученик не разделил сумму и разность аргументов на 2."),
   (r"$\cos 8\alpha$", "Ученик сложил аргументы косинусов.")],
  lambda: same(cos(5 * al) + cos(3 * al), 2 * cos(4 * al) * cos(al)), vals=[2 * cos(4 * al) * cos(al), -2 * sin(4 * al) * sin(al), 2 * cos(8 * al) * cos(2 * al), cos(8 * al)])
T("G9_S27_09", "B", "expression", r"Представьте в виде произведения $\cos 7x + \cos x$.", r"$2\cos 4x\cos 3x$",
  [(r"$2\sin 4x\sin 3x$", "Ученик заменил косинусы синусами в формуле суммы косинусов."), (r"$-2\cos 4x\cos 3x$", "Ученик поставил лишний минус."),
   (r"$2\cos 8x\cos 6x$", "Ученик не разделил сумму и разность аргументов на 2.")],
  lambda: same(cos(7 * x) + cos(x), 2 * cos(4 * x) * cos(3 * x)), vals=[2 * cos(4 * x) * cos(3 * x), 2 * sin(4 * x) * sin(3 * x), -2 * cos(4 * x) * cos(3 * x), 2 * cos(8 * x) * cos(6 * x)])
# S27_19 смешанные выражения
T("G9_S27_19", "B", "expression", r"Упростите выражение $\dfrac{\sin\alpha + \sin\beta}{\cos\alpha + \cos\beta}$.", r"$\operatorname{tg}\dfrac{\alpha + \beta}{2}$",
  [(r"$\operatorname{ctg}\dfrac{\alpha + \beta}{2}$", "Ученик перевернул отношение синуса и косинуса после сокращения."),
   (r"$\operatorname{tg}\dfrac{\alpha - \beta}{2}$", "Ученик сократил не те множители: общий множитель — cos((α − β)/2)."),
   (r"$\operatorname{tg}(\alpha + \beta)$", "Ученик забыл разделить сумму углов на 2.")],
  lambda: same((sin(al) + sin(be)) / (cos(al) + cos(be)), tan((al + be) / 2)), vals=[tan((al + be) / 2), cot((al + be) / 2), tan((al - be) / 2), tan(al + be)])
T("G9_S27_19", "B", "expression", r"Упростите выражение $\dfrac{\sin 5\alpha - \sin 3\alpha}{\cos 5\alpha + \cos 3\alpha}$.", r"$\operatorname{tg}\alpha$",
  [(r"$\operatorname{ctg}\alpha$", "Ученик перевернул отношение после сокращения на 2cos 4α."), (r"$\operatorname{tg} 4\alpha$", "Ученик сократил на sin α и cos α вместо cos 4α."),
   (r"$-\operatorname{tg}\alpha$", "Ученик ошибся в знаке формулы разности синусов.")],
  lambda: same((sin(5 * al) - sin(3 * al)) / (cos(5 * al) + cos(3 * al)), tan(al)), vals=[tan(al), cot(al), tan(4 * al), -tan(al)])
# S25_04 двойной угол
T("G9_S25_04", "A", "exact_number", r"Вычислите $2\sin 75^{\circ}\cos 75^{\circ}$.", r"$\dfrac{1}{2}$",
  [(r"$\dfrac{\sqrt{3}}{2}$", "Ученик взял cos 150° по модулю вместо sin 150°."), (r"$1$", "Ученик решил, что 2 sin α cos α = 1."),
   (r"$-\dfrac{1}{2}$", "Ученик ошибся в знаке sin 150°: угол во II четверти, синус положителен.")],
  lambda: simplify(2 * sin(deg(75)) * cos(deg(75)) - R(1, 2)) == 0, vals=[R(1, 2), sqrt(3) / 2, 1, -R(1, 2)])
# S26_17 уравнение через формулы приведения
T("G9_S26_17", "B", "text", r"Решите уравнение $\cos\left(\dfrac{\pi}{2} - x\right) = \dfrac{\sqrt{3}}{2}$.", r"$x = (-1)^{k}\dfrac{\pi}{3} + \pi k$, $k \in \mathbb{Z}$",
  [(r"$x = \pm\dfrac{\pi}{6} + 2\pi k$, $k \in \mathbb{Z}$", "Ученик не применил формулу приведения и решил уравнение cos x = √3/2."),
   (r"$x = \dfrac{\pi}{3} + 2\pi k$, $k \in \mathbb{Z}$", "Ученик потерял вторую серию решений x = 2π/3 + 2πk."),
   (r"$x = \pm\dfrac{\pi}{3} + 2\pi k$, $k \in \mathbb{Z}$", "Ученик верно получил sin x = √3/2, но записал решение по формуле для косинуса.")],
  lambda: set(solveset(Eq(cos(pi / 2 - x), sqrt(3) / 2), x, Interval.Ropen(0, 2 * pi))) == {pi / 3, 2 * pi / 3})
# S27_01 … S27_07, S27_12
T("G9_S27_01", "B", "exact_number", r"Вычислите $\sin 75^{\circ} + \sin 15^{\circ}$.", r"$\dfrac{\sqrt{6}}{2}$",
  [(r"$1$", "Ученик сложил аргументы: sin 75° + sin 15° ≠ sin 90°."), (r"$\dfrac{\sqrt{2}}{2}$", "Ученик применил формулу разности синусов."),
   (r"$\sqrt{2}$", "Ученик потерял множитель cos 30° в формуле 2 sin 45° cos 30°.")],
  lambda: simplify(sin(deg(75)) + sin(deg(15)) - sqrt(6) / 2) == 0, vals=[sqrt(6) / 2, 1, sqrt(2) / 2, sqrt(2)])
T("G9_S27_02", "B", "exact_number", r"Вычислите $\cos 15^{\circ} - \cos 75^{\circ}$.", r"$\dfrac{\sqrt{2}}{2}$",
  [(r"$-\dfrac{\sqrt{2}}{2}$", "Ученик ошибся в знаке формулы разности косинусов."), (r"$\dfrac{\sqrt{6}}{2}$", "Ученик применил формулу суммы косинусов."),
   (r"$\dfrac{1}{2}$", "Ученик вычел аргументы: cos 15° − cos 75° ≠ cos 60°.")],
  lambda: simplify(cos(deg(15)) - cos(deg(75)) - sqrt(2) / 2) == 0, vals=[sqrt(2) / 2, -sqrt(2) / 2, sqrt(6) / 2, R(1, 2)])
T("G9_S27_03", "A", "expression", r"Упростите $\sin^{2}\alpha - \cos^{2}\alpha$.", r"$-\cos 2\alpha$",
  [(r"$\cos 2\alpha$", "Ученик ошибся в знаке: cos 2α = cos²α − sin²α."), (r"$1$", "Ученик перепутал разность с основным тождеством sin²α + cos²α = 1."),
   (r"$\sin 2\alpha$", "Ученик перепутал формулу косинуса двойного угла с формулой синуса.")],
  lambda: same(sin(al)**2 - cos(al)**2, -cos(2 * al)), vals=[-cos(2 * al), cos(2 * al), Integer(1), sin(2 * al)])
T("G9_S27_05", "B", "exact_number", r"Вычислите $\cos 75^{\circ} + \cos 15^{\circ}$.", r"$\dfrac{\sqrt{6}}{2}$",
  [(r"$\dfrac{\sqrt{2}}{2}$", "Ученик применил формулу разности косинусов."), (r"$0$", "Ученик сложил аргументы: cos 90° = 0."),
   (r"$\sqrt{3}$", "Ученик взял 2 cos 30° и потерял множитель cos 45°.")],
  lambda: simplify(cos(deg(75)) + cos(deg(15)) - sqrt(6) / 2) == 0, vals=[sqrt(6) / 2, sqrt(2) / 2, 0, sqrt(3)])
T("G9_S27_06", "B", "exact_number", r"Вычислите $\sin 75^{\circ} - \sin 15^{\circ}$.", r"$\dfrac{\sqrt{2}}{2}$",
  [(r"$-\dfrac{\sqrt{2}}{2}$", "Ученик ошибся в знаке: sin 75° > sin 15°."), (r"$\dfrac{\sqrt{6}}{2}$", "Ученик применил формулу суммы синусов."),
   (r"$\dfrac{\sqrt{3}}{2}$", "Ученик вычел аргументы: sin 75° − sin 15° ≠ sin 60°.")],
  lambda: simplify(sin(deg(75)) - sin(deg(15)) - sqrt(2) / 2) == 0, vals=[sqrt(2) / 2, -sqrt(2) / 2, sqrt(6) / 2, sqrt(3) / 2])
T("G9_S27_07", "B", "expression", r"Представьте в виде произведения $\sin\dfrac{\pi}{3} + \sin\dfrac{\pi}{6}$.", r"$\sqrt{2}\cos\dfrac{\pi}{12}$",
  [(r"$\sqrt{2}\sin\dfrac{\pi}{12}$", "Ученик поменял косинус на синус во втором множителе формулы суммы синусов."),
   (r"$\sin\dfrac{\pi}{2}$", "Ученик сложил аргументы синусов."),
   (r"$2\sin\dfrac{\pi}{2}\cos\dfrac{\pi}{6}$", "Ученик не разделил сумму и разность аргументов на 2.")],
  lambda: simplify(sin(pi / 3) + sin(pi / 6) - sqrt(2) * cos(pi / 12)) == 0, vals=[sqrt(2) * cos(pi / 12), sqrt(2) * sin(pi / 12), sin(pi / 2), 2 * sin(pi / 2) * cos(pi / 6)])
T("G9_S27_12", "B", "expression", r"Упростите выражение $\dfrac{\sin 3\alpha + \sin\alpha}{\cos 3\alpha + \cos\alpha}$.", r"$\operatorname{tg} 2\alpha$",
  [(r"$\operatorname{ctg} 2\alpha$", "Ученик перевернул отношение после сокращения на 2cos α."), (r"$\operatorname{tg}\alpha$", "Ученик сократил на sin 2α и cos 2α вместо cos α."),
   (r"$\operatorname{tg} 4\alpha$", "Ученик сложил аргументы, не разделив их на 2.")],
  lambda: same((sin(3 * al) + sin(al)) / (cos(3 * al) + cos(al)), tan(2 * al)), vals=[tan(2 * al), cot(2 * al), tan(al), tan(4 * al)])
