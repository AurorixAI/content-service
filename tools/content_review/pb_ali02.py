# -*- coding: utf-8 -*-
# Alimov 9, proof tasks 25–49 (§22–26 identities). 270(1) restored from the scan (idum PDF p. 119): cos 2α, sin² 2α.
# 291(3) is a misprint in the book itself (identity false) — deactivated separately, not rewritten here.
# Unchanged: 30, 38, 39, 44, 46.
NOT = r", поэтому тождество неверно."
P = {
"G9_TB_22_265_2": {
 "k": r"$2 - \sin^{2}\alpha - \cos^{2}\alpha = 2 - (\sin^{2}\alpha + \cos^{2}\alpha) = 2 - 1 = 1$.",
 "d": [(r"$2 - \sin^{2}\alpha - \cos^{2}\alpha = 2 - 1 - 1 = 0$, так как $\sin^{2}\alpha = 1$ и $\cos^{2}\alpha = 1$" + NOT, r"Единице равна сумма $\sin^{2}\alpha + \cos^{2}\alpha$, а не каждое слагаемое."),
       (r"$2 - \sin^{2}\alpha - \cos^{2}\alpha = 2 - (\sin\alpha + \cos\alpha)^{2} = 2 - 1 = 1$.", r"$\sin^{2}\alpha + \cos^{2}\alpha \ne (\sin\alpha + \cos\alpha)^{2}$, и $(\sin\alpha + \cos\alpha)^{2}$ не всегда равно $1$."),
       (r"$2 - \sin^{2}\alpha - \cos^{2}\alpha = 2 - (\sin^{2}\alpha - \cos^{2}\alpha) = 2 - 1 = 1$.", r"При вынесении «−» за скобку знак перед $\cos^{2}\alpha$ меняется: $-(\sin^{2}\alpha + \cos^{2}\alpha)$; к тому же $\sin^{2}\alpha - \cos^{2}\alpha \ne 1$.")]},
"G9_TB_22_265_3": {
 "k": r"$1 - \sin^{2}\alpha = \cos^{2}\alpha$, поэтому левая часть равна $\dfrac{\sin^{2}\alpha}{\cos^{2}\alpha} = \operatorname{tg}^{2}\alpha$.",
 "d": [(r"$1 - \sin^{2}\alpha = \cos^{2}\alpha$, поэтому левая часть равна $\dfrac{\sin^{2}\alpha}{\cos^{2}\alpha} = \operatorname{ctg}^{2}\alpha$" + NOT, r"$\dfrac{\sin\alpha}{\cos\alpha} = \operatorname{tg}\alpha$."),
       (r"$1 - \sin^{2}\alpha = \cos\alpha$, поэтому левая часть равна $\dfrac{\sin^{2}\alpha}{\cos\alpha}$" + NOT, r"$1 - \sin^{2}\alpha = \cos^{2}\alpha$: квадрат потерян."),
       (r"$1 - \sin^{2}\alpha = -\cos^{2}\alpha$, поэтому левая часть равна $-\operatorname{tg}^{2}\alpha$" + NOT, r"Из $\sin^{2}\alpha + \cos^{2}\alpha = 1$ следует $1 - \sin^{2}\alpha = \cos^{2}\alpha$ без знака «−».")]},
"G9_TB_22_265_4": {
 "k": r"$1 - \cos^{2}\alpha = \sin^{2}\alpha$, поэтому левая часть равна $\dfrac{\cos^{2}\alpha}{\sin^{2}\alpha} = \operatorname{ctg}^{2}\alpha$.",
 "d": [(r"$1 - \cos^{2}\alpha = \sin^{2}\alpha$, поэтому левая часть равна $\dfrac{\cos^{2}\alpha}{\sin^{2}\alpha} = \operatorname{tg}^{2}\alpha$" + NOT, r"$\dfrac{\cos\alpha}{\sin\alpha} = \operatorname{ctg}\alpha$."),
       (r"$\dfrac{\cos^{2}\alpha}{1 - \cos^{2}\alpha} = \dfrac{1}{1 - 1} $, т. е. дробь не определена" + NOT, r"$\cos^{2}\alpha$ нельзя сократить с частью разности $1 - \cos^{2}\alpha$."),
       (r"$1 - \cos^{2}\alpha = \sin^{2}\alpha$, поэтому левая часть равна $\cos^{2}\alpha \cdot \sin^{2}\alpha$" + NOT, r"Знаменатель $\sin^{2}\alpha$ делит, а не умножает: $\dfrac{\cos^{2}\alpha}{\sin^{2}\alpha}$.")]},
"G9_TB_22_265_5": {
 "k": r"$1 + \operatorname{tg}^{2}\alpha = \dfrac{1}{\cos^{2}\alpha}$, поэтому $\dfrac{1}{1 + \operatorname{tg}^{2}\alpha} = \cos^{2}\alpha$, и левая часть равна $\cos^{2}\alpha + \sin^{2}\alpha = 1$.",
 "d": [(r"$1 + \operatorname{tg}^{2}\alpha = \dfrac{1}{\sin^{2}\alpha}$, поэтому левая часть равна $2\sin^{2}\alpha$" + NOT, r"$1 + \operatorname{tg}^{2}\alpha = \dfrac{\cos^{2}\alpha + \sin^{2}\alpha}{\cos^{2}\alpha} = \dfrac{1}{\cos^{2}\alpha}$."),
       (r"$\dfrac{1}{1 + \operatorname{tg}^{2}\alpha} = 1 + \operatorname{ctg}^{2}\alpha$, поэтому левая часть равна $1 + \operatorname{ctg}^{2}\alpha + \sin^{2}\alpha$" + NOT, r"Обратная величина суммы не равна сумме обратных величин."),
       (r"$1 + \operatorname{tg}^{2}\alpha = \cos^{2}\alpha$, поэтому левая часть равна $\dfrac{1}{\cos^{2}\alpha} + \sin^{2}\alpha$" + NOT, r"$1 + \operatorname{tg}^{2}\alpha = \dfrac{1}{\cos^{2}\alpha}$; перевёрнута дробь.")]},
"G9_TB_22_265_6": {
 "k": r"$1 + \operatorname{ctg}^{2}\alpha = \dfrac{1}{\sin^{2}\alpha}$, поэтому $\dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = \sin^{2}\alpha$, и левая часть равна $\sin^{2}\alpha + \cos^{2}\alpha = 1$.",
 "d": [(r"$1 + \operatorname{ctg}^{2}\alpha = \dfrac{1}{\cos^{2}\alpha}$, поэтому левая часть равна $2\cos^{2}\alpha$" + NOT, r"$1 + \operatorname{ctg}^{2}\alpha = \dfrac{\sin^{2}\alpha + \cos^{2}\alpha}{\sin^{2}\alpha} = \dfrac{1}{\sin^{2}\alpha}$."),
       (r"$\dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = 1 + \operatorname{tg}^{2}\alpha$, поэтому левая часть равна $1 + \operatorname{tg}^{2}\alpha + \cos^{2}\alpha$" + NOT, r"Обратная величина суммы не равна сумме обратных величин."),
       (r"$\dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = \operatorname{tg}^{2}\alpha$, поэтому левая часть равна $\operatorname{tg}^{2}\alpha + \cos^{2}\alpha$" + NOT, r"$\dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = \sin^{2}\alpha$; дробь $\dfrac{1}{\operatorname{ctg}^{2}\alpha}$ получилась бы без слагаемого $1$.")]},
"G9_TB_22_268_2": {
 "k": r"$\sin^{2}\alpha(1 + \operatorname{ctg}^{2}\alpha) = \sin^{2}\alpha \cdot \dfrac{1}{\sin^{2}\alpha} = 1$, поэтому левая часть равна $1 - \cos^{2}\alpha = \sin^{2}\alpha$.",
 "d": [(r"$\sin^{2}\alpha(1 + \operatorname{ctg}^{2}\alpha) = \sin^{2}\alpha + \cos^{2}\alpha \cdot \sin^{2}\alpha$, поэтому левая часть равна $\sin^{2}\alpha + \cos^{2}\alpha\sin^{2}\alpha - \cos^{2}\alpha$" + NOT, r"$\sin^{2}\alpha \cdot \operatorname{ctg}^{2}\alpha = \sin^{2}\alpha \cdot \dfrac{\cos^{2}\alpha}{\sin^{2}\alpha} = \cos^{2}\alpha$."),
       (r"$1 + \operatorname{ctg}^{2}\alpha = \dfrac{1}{\cos^{2}\alpha}$, поэтому левая часть равна $\operatorname{tg}^{2}\alpha - \cos^{2}\alpha$" + NOT, r"$1 + \operatorname{ctg}^{2}\alpha = \dfrac{1}{\sin^{2}\alpha}$."),
       (r"$\sin^{2}\alpha(1 + \operatorname{ctg}^{2}\alpha) = 1$, поэтому левая часть равна $1 - \cos^{2}\alpha = \cos^{2}\alpha$" + NOT, r"$1 - \cos^{2}\alpha = \sin^{2}\alpha$.")]},
"G9_TB_22_270_1": {
 "q": r"Докажите тождество: $(1 - \cos 2\alpha)(1 + \cos 2\alpha) = \sin^{2} 2\alpha$",
 "qwhy": "в условии был потерян аргумент 2α ((1 − cos²α)(1 + cos²α) = sin²α — неверное равенство, ключ был «Тождество неверно»); формулировка сверена со сканом учебника (с. 119, № 270)",
 "k": r"$(1 - \cos 2\alpha)(1 + \cos 2\alpha) = 1 - \cos^{2} 2\alpha = \sin^{2} 2\alpha$ по основному тригонометрическому тождеству для угла $2\alpha$.",
 "d": [(r"$(1 - \cos 2\alpha)(1 + \cos 2\alpha) = 1 + \cos^{2} 2\alpha$" + NOT, r"Произведение разности и суммы равно разности квадратов: $1 - \cos^{2} 2\alpha$."),
       (r"$(1 - \cos 2\alpha)(1 + \cos 2\alpha) = 1 - \cos^{2} 2\alpha = \cos^{2} 2\alpha$" + NOT, r"$1 - \cos^{2} 2\alpha = \sin^{2} 2\alpha$."),
       (r"$(1 - \cos 2\alpha)(1 + \cos 2\alpha) = 1 - \cos^{2} 2\alpha = \sin^{2}\alpha$" + NOT, r"Основное тождество применяется к тому же углу $2\alpha$: $1 - \cos^{2} 2\alpha = \sin^{2} 2\alpha$.")]},
"G9_TB_22_270_2": {
 "k": r"$\cos^{2}\alpha = 1 - \sin^{2}\alpha = (1 - \sin\alpha)(1 + \sin\alpha)$, поэтому $\dfrac{\sin\alpha - 1}{\cos^{2}\alpha} = \dfrac{-(1 - \sin\alpha)}{(1 - \sin\alpha)(1 + \sin\alpha)} = -\dfrac{1}{1 + \sin\alpha}$.",
 "d": [(r"$\dfrac{\sin\alpha - 1}{(1 - \sin\alpha)(1 + \sin\alpha)} = \dfrac{1}{1 + \sin\alpha}$" + NOT, r"$\sin\alpha - 1 = -(1 - \sin\alpha)$: после сокращения остаётся знак «−»."),
       (r"$\cos^{2}\alpha = (1 - \sin\alpha)^{2}$, поэтому левая часть равна $-\dfrac{1}{1 - \sin\alpha}$" + NOT, r"$\cos^{2}\alpha = 1 - \sin^{2}\alpha = (1 - \sin\alpha)(1 + \sin\alpha)$, а не $(1 - \sin\alpha)^{2}$."),
       (r"$\cos^{2}\alpha = \sin^{2}\alpha - 1$, поэтому левая часть равна $\dfrac{\sin\alpha - 1}{(\sin\alpha - 1)(\sin\alpha + 1)} = \dfrac{1}{1 + \sin\alpha}$" + NOT, r"$\cos^{2}\alpha = 1 - \sin^{2}\alpha$, а не $\sin^{2}\alpha - 1$.")]},
"G9_TB_22_270_3": {
 "k": r"$\cos^{4}\alpha - \sin^{4}\alpha = (\cos^{2}\alpha - \sin^{2}\alpha)(\cos^{2}\alpha + \sin^{2}\alpha) = \cos^{2}\alpha - \sin^{2}\alpha$.",
 "d": [(r"$\cos^{4}\alpha - \sin^{4}\alpha = (\cos^{2}\alpha - \sin^{2}\alpha)^{2}$" + NOT, r"Разность четвёртых степеней — произведение разности и суммы квадратов, а не квадрат разности."),
       (r"$\cos^{4}\alpha - \sin^{4}\alpha = (\cos^{2}\alpha + \sin^{2}\alpha)^{2} = 1$" + NOT, r"$(\cos^{2}\alpha + \sin^{2}\alpha)^{2} = \cos^{4}\alpha + 2\cos^{2}\alpha\sin^{2}\alpha + \sin^{4}\alpha$."),
       (r"$\cos^{4}\alpha - \sin^{4}\alpha = (\cos\alpha - \sin\alpha)^{4}$, и это не равно $\cos^{2}\alpha - \sin^{2}\alpha$" + NOT, r"Разность степеней не равна степени разности.")]},
"G9_TB_22_270_5": {
 "k": r"$\dfrac{\sin\alpha}{1 + \cos\alpha} + \dfrac{1 + \cos\alpha}{\sin\alpha} = \dfrac{\sin^{2}\alpha + 1 + 2\cos\alpha + \cos^{2}\alpha}{\sin\alpha(1 + \cos\alpha)} = \dfrac{2(1 + \cos\alpha)}{\sin\alpha(1 + \cos\alpha)} = \dfrac{2}{\sin\alpha}$.",
 "d": [(r"Числитель $\sin^{2}\alpha + (1 + \cos\alpha)^{2} = \sin^{2}\alpha + 1 + \cos^{2}\alpha = 2$, поэтому левая часть равна $\dfrac{2}{\sin\alpha(1 + \cos\alpha)}$" + NOT, r"$(1 + \cos\alpha)^{2} = 1 + 2\cos\alpha + \cos^{2}\alpha$: удвоенное произведение потеряно."),
       (r"$\dfrac{\sin\alpha}{1 + \cos\alpha} + \dfrac{1 + \cos\alpha}{\sin\alpha} = \dfrac{\sin\alpha + 1 + \cos\alpha}{1 + \cos\alpha + \sin\alpha} = 1$" + NOT, r"Дроби складывают через общий знаменатель, а не складывая числители и знаменатели."),
       (r"Числитель равен $2(1 + \cos\alpha)$, знаменатель $\sin\alpha(1 + \cos\alpha)$, поэтому левая часть равна $\dfrac{2}{1 + \cos\alpha}$" + NOT, r"Сокращается множитель $1 + \cos\alpha$, и остаётся $\dfrac{2}{\sin\alpha}$.")]},
"G9_TB_22_270_6": {
 "k": r"Умножим числитель и знаменатель левой части на $1 + \cos\alpha$: $\dfrac{\sin\alpha(1 + \cos\alpha)}{1 - \cos^{2}\alpha} = \dfrac{\sin\alpha(1 + \cos\alpha)}{\sin^{2}\alpha} = \dfrac{1 + \cos\alpha}{\sin\alpha}$.",
 "d": [(r"Умножим числитель и знаменатель на $1 + \cos\alpha$: $\dfrac{\sin\alpha(1 + \cos\alpha)}{1 + \cos^{2}\alpha}$, и это не равно правой части" + NOT, r"$(1 - \cos\alpha)(1 + \cos\alpha) = 1 - \cos^{2}\alpha = \sin^{2}\alpha$."),
       (r"При $\alpha = 0$ знаменатель $1 - \cos\alpha$ равен нулю" + NOT, r"Тождество доказывают для допустимых значений $\alpha$; точка $\alpha = 0$ в них не входит."),
       (r"$\dfrac{\sin\alpha}{1 - \cos\alpha} = \dfrac{1}{1 - \operatorname{ctg}\alpha}$, и это не равно правой части" + NOT, r"Разделив числитель и знаменатель на $\sin\alpha$, получаем $\dfrac{1}{\frac{1}{\sin\alpha} - \operatorname{ctg}\alpha}$, а не $\dfrac{1}{1 - \operatorname{ctg}\alpha}$.")]},
"G9_TB_22_270_7": {
 "k": r"$\dfrac{1}{1 + \operatorname{tg}^{2}\alpha} = \cos^{2}\alpha$ и $\dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = \sin^{2}\alpha$, поэтому левая часть равна $\cos^{2}\alpha + \sin^{2}\alpha = 1$.",
 "d": [(r"$\dfrac{1}{1 + \operatorname{tg}^{2}\alpha} = \sin^{2}\alpha$ и $\dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = \cos^{2}\alpha$, поэтому левая часть равна $1$.", r"$1 + \operatorname{tg}^{2}\alpha = \dfrac{1}{\cos^{2}\alpha}$, поэтому первая дробь равна $\cos^{2}\alpha$; ответ совпал, но формулы перепутаны."),
       (r"$\dfrac{1}{1 + \operatorname{tg}^{2}\alpha} + \dfrac{1}{1 + \operatorname{ctg}^{2}\alpha} = \dfrac{2}{2 + \operatorname{tg}^{2}\alpha + \operatorname{ctg}^{2}\alpha}$" + NOT, r"Дроби складывают через общий знаменатель, а не складывая числители и знаменатели."),
       (r"При $\alpha = 45^{\circ}$ и $\alpha = 30^{\circ}$ сумма равна $1$, поэтому тождество верно.", r"Проверка в отдельных точках не доказывает тождества.")]},
"G9_TB_25_291_1": {
 "k": r"$\sin(\alpha - \beta)\sin(\alpha + \beta) = \sin^{2}\alpha\cos^{2}\beta - \cos^{2}\alpha\sin^{2}\beta = \sin^{2}\alpha(1 - \sin^{2}\beta) - (1 - \sin^{2}\alpha)\sin^{2}\beta = \sin^{2}\alpha - \sin^{2}\beta$.",
 "d": [(r"$\sin(\alpha - \beta)\sin(\alpha + \beta) = \sin^{2}\alpha\cos^{2}\beta + \cos^{2}\alpha\sin^{2}\beta$" + NOT, r"Произведение разности и суммы — разность квадратов: $\sin^{2}\alpha\cos^{2}\beta - \cos^{2}\alpha\sin^{2}\beta$."),
       (r"$\sin(\alpha - \beta)\sin(\alpha + \beta) = (\sin\alpha - \sin\beta)(\sin\alpha + \sin\beta) = \sin^{2}\alpha - \sin^{2}\beta$.", r"Синус разности и суммы не равен разности и сумме синусов; ответ совпал случайно."),
       (r"$\sin(\alpha - \beta)\sin(\alpha + \beta) = \sin(\alpha^{2} - \beta^{2})$" + NOT, r"Произведение синусов не равно синусу произведения аргументов.")]},
"G9_TB_25_291_2": {
 "k": r"$\cos(\alpha - \beta)\cos(\alpha + \beta) = \cos^{2}\alpha\cos^{2}\beta - \sin^{2}\alpha\sin^{2}\beta = \cos^{2}\alpha(1 - \sin^{2}\beta) - (1 - \cos^{2}\alpha)\sin^{2}\beta = \cos^{2}\alpha - \sin^{2}\beta$.",
 "d": [(r"$\cos(\alpha - \beta)\cos(\alpha + \beta) = \cos^{2}\alpha\cos^{2}\beta + \sin^{2}\alpha\sin^{2}\beta$" + NOT, r"Произведение разности и суммы — разность квадратов: $\cos^{2}\alpha\cos^{2}\beta - \sin^{2}\alpha\sin^{2}\beta$."),
       (r"$\cos(\alpha - \beta)\cos(\alpha + \beta) = (\cos\alpha - \cos\beta)(\cos\alpha + \cos\beta) = \cos^{2}\alpha - \cos^{2}\beta$" + NOT, r"Косинус разности и суммы не равен разности и сумме косинусов."),
       (r"$\cos(\alpha - \beta)\cos(\alpha + \beta) = \cos(\alpha^{2} - \beta^{2})$" + NOT, r"Произведение косинусов не равно косинусу произведения аргументов.")]},
"G9_TB_25_291_4": {
 "k": r"Числитель $\cos\alpha - 2\left(\dfrac{1}{2}\cos\alpha - \dfrac{\sqrt{3}}{2}\sin\alpha\right) = \sqrt{3}\sin\alpha$, знаменатель $2\left(\dfrac{\sqrt{3}}{2}\sin\alpha - \dfrac{1}{2}\cos\alpha\right) - \sqrt{3}\sin\alpha = -\cos\alpha$, поэтому дробь равна $-\sqrt{3}\operatorname{tg}\alpha$.",
 "d": [(r"Числитель $\cos\alpha - 2\left(\dfrac{1}{2}\cos\alpha + \dfrac{\sqrt{3}}{2}\sin\alpha\right) = -\sqrt{3}\sin\alpha$, знаменатель $-\cos\alpha$, поэтому дробь равна $\sqrt{3}\operatorname{tg}\alpha$" + NOT, r"$\cos\left(\dfrac{\pi}{3} + \alpha\right) = \cos\dfrac{\pi}{3}\cos\alpha - \sin\dfrac{\pi}{3}\sin\alpha$: знак «−»."),
       (r"Числитель равен $\sqrt{3}\sin\alpha$, знаменатель $2\left(\dfrac{1}{2}\sin\alpha - \dfrac{\sqrt{3}}{2}\cos\alpha\right) - \sqrt{3}\sin\alpha$, и дробь не равна $-\sqrt{3}\operatorname{tg}\alpha$" + NOT, r"$\cos\dfrac{\pi}{6} = \dfrac{\sqrt{3}}{2}$, $\sin\dfrac{\pi}{6} = \dfrac{1}{2}$: значения перепутаны."),
       (r"При $\alpha = 0$ числитель равен $0$, а знаменатель $-1$, поэтому дробь равна $0$, и тождество неверно.", r"При $\alpha = 0$ правая часть тоже равна $-\sqrt{3}\operatorname{tg} 0 = 0$: проверка не опровергает тождества.")]},
"G9_TB_26_299_2": {
 "k": r"$(\sin\alpha - \cos\alpha)^{2} = \sin^{2}\alpha + \cos^{2}\alpha - 2\sin\alpha\cos\alpha = 1 - \sin 2\alpha$.",
 "d": [(r"$(\sin\alpha - \cos\alpha)^{2} = \sin^{2}\alpha + \cos^{2}\alpha + 2\sin\alpha\cos\alpha = 1 + \sin 2\alpha$" + NOT, r"В квадрате разности удвоенное произведение со знаком «−»."),
       (r"$(\sin\alpha - \cos\alpha)^{2} = \sin^{2}\alpha - \cos^{2}\alpha = -\cos 2\alpha$" + NOT, r"Квадрат разности не равен разности квадратов."),
       (r"$(\sin\alpha - \cos\alpha)^{2} = 1 - 2\sin\alpha\cos\alpha = 1 - \sin\alpha$" + NOT, r"$2\sin\alpha\cos\alpha = \sin 2\alpha$, а не $\sin\alpha$.")]},
"G9_TB_26_299_4": {
 "k": r"$\cos 2\alpha = 2\cos^{2}\alpha - 1$, поэтому $2\cos^{2}\alpha - \cos 2\alpha = 2\cos^{2}\alpha - 2\cos^{2}\alpha + 1 = 1$.",
 "d": [(r"$\cos 2\alpha = 2\cos^{2}\alpha + 1$, поэтому левая часть равна $-1$" + NOT, r"$\cos 2\alpha = 2\cos^{2}\alpha - 1$."),
       (r"$2\cos^{2}\alpha - \cos 2\alpha = 2\cos^{2}\alpha - 2\cos^{2}\alpha - 1 = -1$" + NOT, r"При раскрытии скобок $-(2\cos^{2}\alpha - 1)$ знак перед единицей меняется на «+»."),
       (r"$\cos 2\alpha = 2\cos\alpha$, поэтому левая часть равна $2\cos^{2}\alpha - 2\cos\alpha$" + NOT, r"$\cos 2\alpha \ne 2\cos\alpha$; формула двойного угла: $\cos 2\alpha = 2\cos^{2}\alpha - 1$.")]},
"G9_TB_26_301_1": {
 "k": r"$\cos 2\alpha = 2\cos^{2}\alpha - 1$, поэтому $1 + \cos 2\alpha = 2\cos^{2}\alpha$.",
 "d": [(r"$\cos 2\alpha = 1 - 2\cos^{2}\alpha$, поэтому $1 + \cos 2\alpha = 2 - 2\cos^{2}\alpha = 2\sin^{2}\alpha$" + NOT, r"$\cos 2\alpha = 2\cos^{2}\alpha - 1 = 1 - 2\sin^{2}\alpha$; выражения перепутаны."),
       (r"$\cos 2\alpha = 2\sin\alpha\cos\alpha$, поэтому $1 + \cos 2\alpha = (\sin\alpha + \cos\alpha)^{2}$" + NOT, r"$2\sin\alpha\cos\alpha = \sin 2\alpha$, а не $\cos 2\alpha$."),
       (r"$1 + \cos 2\alpha = 2\cos\alpha$, так как $\cos 2\alpha = 2\cos\alpha - 1$" + NOT, r"Формула двойного угла содержит квадрат: $\cos 2\alpha = 2\cos^{2}\alpha - 1$.")]},
"G9_TB_26_301_2": {
 "k": r"$\cos 2\alpha = 1 - 2\sin^{2}\alpha$, поэтому $1 - \cos 2\alpha = 2\sin^{2}\alpha$.",
 "d": [(r"$1 - \cos 2\alpha = 1 - \cos^{2}\alpha + \sin^{2}\alpha = 2\sin^{2}\alpha + 1$" + NOT, r"$1 - \cos^{2}\alpha + \sin^{2}\alpha = \sin^{2}\alpha + \sin^{2}\alpha = 2\sin^{2}\alpha$: единица уже учтена."),
       (r"$\cos 2\alpha = 2\sin\alpha\cos\alpha$, поэтому $1 - \cos 2\alpha = 1 - \sin 2\alpha$" + NOT, r"$2\sin\alpha\cos\alpha = \sin 2\alpha$, а не $\cos 2\alpha$."),
       (r"$\cos 2\alpha = 1 + 2\sin^{2}\alpha$, поэтому $1 - \cos 2\alpha = -2\sin^{2}\alpha$" + NOT, r"$\cos 2\alpha = 1 - 2\sin^{2}\alpha$.")]},
}
