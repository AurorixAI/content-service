# -*- coding: utf-8 -*-
# Generated (no-book) proof tasks. All identities checked numerically; 4 false ones and 2 exact duplicates deactivated separately.
# Unchanged: 2, 6, 15, 17, 19, 22.
NOT = r", поэтому тождество неверно."
SUMF = r"Сумма синусов не равна синусу суммы углов."
P = {
"ds_llm_00631f447a04": {
 "k": r"$\cos 2\alpha - \cos 6\alpha = 2\sin 4\alpha\sin 2\alpha$ и $\sin 6\alpha + \sin 2\alpha = 2\sin 4\alpha\cos 2\alpha$, поэтому дробь равна $\dfrac{\sin 2\alpha}{\cos 2\alpha} = \operatorname{tg} 2\alpha$.",
 "d": [(r"$\cos 2\alpha - \cos 6\alpha = -2\sin 4\alpha\sin 2\alpha$, поэтому дробь равна $-\operatorname{tg} 2\alpha$" + NOT, r"$\cos x - \cos y = -2\sin\dfrac{x + y}{2}\sin\dfrac{x - y}{2}$, а $\sin\dfrac{2\alpha - 6\alpha}{2} = -\sin 2\alpha$: минусы сокращаются."),
       (r"$\sin 6\alpha + \sin 2\alpha = 2\cos 4\alpha\sin 2\alpha$, поэтому дробь равна $\operatorname{tg} 4\alpha$" + NOT, r"$\sin x + \sin y = 2\sin\dfrac{x + y}{2}\cos\dfrac{x - y}{2} = 2\sin 4\alpha\cos 2\alpha$."),
       (r"$\cos 2\alpha - \cos 6\alpha = \cos(-4\alpha)$ и $\sin 6\alpha + \sin 2\alpha = \sin 8\alpha$, поэтому дробь не равна $\operatorname{tg} 2\alpha$.", r"Разность косинусов не равна косинусу разности, а сумма синусов — синусу суммы.")]},
"ds_llm_153d85e0bc39": {
 "k": r"$\sin 2\alpha + \sin 4\alpha = 2\sin 3\alpha\cos\alpha$ и $\cos 2\alpha - \cos 4\alpha = 2\sin 3\alpha\sin\alpha$, поэтому дробь равна $\dfrac{\cos\alpha}{\sin\alpha} = \operatorname{ctg}\alpha$.",
 "d": [(r"$\cos 2\alpha - \cos 4\alpha = -2\sin 3\alpha\sin\alpha$, поэтому дробь равна $-\operatorname{ctg}\alpha$" + NOT, r"$\sin\dfrac{2\alpha - 4\alpha}{2} = -\sin\alpha$, и минусы сокращаются: знаменатель $2\sin 3\alpha\sin\alpha$."),
       (r"$\sin 2\alpha + \sin 4\alpha = 2\cos 3\alpha\sin\alpha$, поэтому дробь равна $\dfrac{\cos 3\alpha}{\sin 3\alpha} = \operatorname{ctg} 3\alpha$" + NOT, r"В формуле суммы синусов синус берётся от полусуммы: $2\sin 3\alpha\cos\alpha$."),
       (r"$\dfrac{\sin 2\alpha + \sin 4\alpha}{\cos 2\alpha - \cos 4\alpha} = \dfrac{\sin 6\alpha}{\cos(-2\alpha)}$" + NOT, SUMF)]},
"ds_llm_1931248be21b": {
 "k": r"По формуле разности квадратов $(\operatorname{tg}\alpha + \operatorname{ctg}\alpha)^{2} - (\operatorname{tg}\alpha - \operatorname{ctg}\alpha)^{2} = 2\operatorname{tg}\alpha \cdot 2\operatorname{ctg}\alpha = 4\operatorname{tg}\alpha\operatorname{ctg}\alpha = 4$.",
 "d": [(r"$(\operatorname{tg}\alpha + \operatorname{ctg}\alpha)^{2} - (\operatorname{tg}\alpha - \operatorname{ctg}\alpha)^{2} = (\operatorname{tg}^{2}\alpha + \operatorname{ctg}^{2}\alpha) - (\operatorname{tg}^{2}\alpha - \operatorname{ctg}^{2}\alpha) = 2\operatorname{ctg}^{2}\alpha$" + NOT, r"Квадрат суммы и разности содержит удвоенное произведение $\pm 2\operatorname{tg}\alpha\operatorname{ctg}\alpha$."),
       (r"Левая часть равна $4\operatorname{tg}\alpha\operatorname{ctg}\alpha$, а $\operatorname{tg}\alpha\operatorname{ctg}\alpha = \operatorname{tg}^{2}\alpha$" + NOT, r"$\operatorname{tg}\alpha \cdot \operatorname{ctg}\alpha = 1$."),
       (r"Левая часть равна $2\operatorname{tg}\alpha\operatorname{ctg}\alpha = 2$" + NOT, r"$(u + v)^{2} - (u - v)^{2} = 4uv$, а не $2uv$.")]},
"ds_llm_2afc9995cd8c": {
 "k": r"$1 - \sin^{2}\alpha = \cos^{2}\alpha$, поэтому левая часть равна $\dfrac{\sin^{2}\alpha}{\cos^{2}\alpha} = \operatorname{tg}^{2}\alpha$ (при $\cos\alpha \ne 0$).",
 "d": [(r"$1 - \sin^{2}\alpha = \cos\alpha$, поэтому левая часть равна $\dfrac{\sin^{2}\alpha}{\cos\alpha}$" + NOT, r"$1 - \sin^{2}\alpha = \cos^{2}\alpha$."),
       (r"$1 - \sin^{2}\alpha = \cos^{2}\alpha$, поэтому левая часть равна $\operatorname{ctg}^{2}\alpha$" + NOT, r"$\dfrac{\sin\alpha}{\cos\alpha} = \operatorname{tg}\alpha$."),
       (r"При $\alpha = 90^{\circ}$ левая часть не определена, поэтому равенство не является тождеством.", r"Тождество доказывают на области допустимых значений; $\alpha = 90^{\circ}$ в неё не входит.")]},
"ds_llm_3006d6cd151b": {
 "k": r"$\sin 7\alpha - \sin 3\alpha = 2\sin 2\alpha\cos 5\alpha$ и $\cos 7\alpha + \cos 3\alpha = 2\cos 5\alpha\cos 2\alpha$, поэтому дробь равна $\operatorname{tg} 2\alpha$.",
 "d": [(r"$\sin 7\alpha - \sin 3\alpha = 2\cos 2\alpha\sin 5\alpha$, поэтому дробь равна $\operatorname{tg} 5\alpha$" + NOT, r"$\sin x - \sin y = 2\sin\dfrac{x - y}{2}\cos\dfrac{x + y}{2} = 2\sin 2\alpha\cos 5\alpha$."),
       (r"$\cos 7\alpha + \cos 3\alpha = -2\sin 5\alpha\sin 2\alpha$, поэтому дробь равна $-\operatorname{ctg} 5\alpha$" + NOT, r"$\cos x + \cos y = 2\cos\dfrac{x + y}{2}\cos\dfrac{x - y}{2}$."),
       (r"$\sin 7\alpha - \sin 3\alpha = \sin 4\alpha$ и $\cos 7\alpha + \cos 3\alpha = \cos 10\alpha$" + NOT, SUMF)]},
"ds_llm_6136ea25f274": {
 "k": r"$\sin 5\alpha - \sin 3\alpha = 2\sin\dfrac{5\alpha - 3\alpha}{2}\cos\dfrac{5\alpha + 3\alpha}{2} = 2\sin\alpha\cos 4\alpha$.",
 "d": [(r"$\sin 5\alpha - \sin 3\alpha = 2\cos\alpha\sin 4\alpha$" + NOT, r"В формуле разности синусов синус берётся от полуразности, косинус — от полусуммы."),
       (r"$\sin 5\alpha - \sin 3\alpha = \sin 2\alpha = 2\sin\alpha\cos\alpha$" + NOT, r"Разность синусов не равна синусу разности углов."),
       (r"$\sin 5\alpha - \sin 3\alpha = 4\sin\alpha\cos 4\alpha$" + NOT, r"В формуле множитель $2$, а не $4$.")]},
"ds_llm_613af5ca35a6": {
 "k": r"$\operatorname{tg}\alpha \pm \operatorname{ctg}\alpha = \dfrac{\sin^{2}\alpha \pm \cos^{2}\alpha}{\sin\alpha\cos\alpha}$, поэтому дробь равна $\dfrac{\sin^{2}\alpha + \cos^{2}\alpha}{\sin^{2}\alpha - \cos^{2}\alpha} = \dfrac{1}{\sin^{2}\alpha - \cos^{2}\alpha}$.",
 "d": [(r"$\operatorname{tg}\alpha + \operatorname{ctg}\alpha = 1$ и $\operatorname{tg}\alpha - \operatorname{ctg}\alpha = 0$, поэтому дробь не определена" + NOT, r"$\operatorname{tg}\alpha \cdot \operatorname{ctg}\alpha = 1$, но сумма и разность вычисляются через общий знаменатель $\sin\alpha\cos\alpha$."),
       (r"Дробь равна $\dfrac{\sin^{2}\alpha + \cos^{2}\alpha}{\cos^{2}\alpha - \sin^{2}\alpha} = \dfrac{1}{\cos 2\alpha}$" + NOT, r"$\operatorname{tg}\alpha - \operatorname{ctg}\alpha = \dfrac{\sin^{2}\alpha - \cos^{2}\alpha}{\sin\alpha\cos\alpha}$: порядок вычитания перепутан."),
       (r"Дробь равна $\dfrac{\operatorname{tg}\alpha}{\operatorname{tg}\alpha} \cdot \dfrac{\operatorname{ctg}\alpha}{-\operatorname{ctg}\alpha} = -1$" + NOT, r"Сокращать можно только общие множители числителя и знаменателя, а не слагаемые.")]},
"ds_llm_63a6fed490c9": {
 "k": r"$\dfrac{1 - \sin\alpha}{\cos\alpha} + \dfrac{\cos\alpha}{1 - \sin\alpha} = \dfrac{(1 - \sin\alpha)^{2} + \cos^{2}\alpha}{\cos\alpha(1 - \sin\alpha)} = \dfrac{2 - 2\sin\alpha}{\cos\alpha(1 - \sin\alpha)} = \dfrac{2}{\cos\alpha}$.",
 "d": [(r"Числитель $(1 - \sin\alpha)^{2} + \cos^{2}\alpha = 1 + \sin^{2}\alpha + \cos^{2}\alpha = 2$, поэтому левая часть равна $\dfrac{2}{\cos\alpha(1 - \sin\alpha)}$" + NOT, r"$(1 - \sin\alpha)^{2} = 1 - 2\sin\alpha + \sin^{2}\alpha$: удвоенное произведение потеряно."),
       (r"Числитель равен $2(1 - \sin\alpha)$, знаменатель $\cos\alpha(1 - \sin\alpha)$, поэтому левая часть равна $\dfrac{2}{1 - \sin\alpha}$" + NOT, r"После сокращения на $1 - \sin\alpha$ остаётся $\dfrac{2}{\cos\alpha}$."),
       (r"$\dfrac{1 - \sin\alpha}{\cos\alpha} + \dfrac{\cos\alpha}{1 - \sin\alpha} = \dfrac{1 - \sin\alpha + \cos\alpha}{\cos\alpha + 1 - \sin\alpha} = 1$" + NOT, r"Дроби складывают через общий знаменатель.")]},
"ds_llm_6fed4060748e": {
 "k": r"$\sin\alpha + \sin 5\alpha = 2\sin 3\alpha\cos 2\alpha$, поэтому левая часть равна $\sin 3\alpha(1 + 2\cos 2\alpha)$, а $1 + 2\cos 2\alpha = 3 - 4\sin^{2}\alpha = \dfrac{\sin 3\alpha}{\sin\alpha}$.",
 "d": [(r"$\sin\alpha + \sin 5\alpha = 2\sin 3\alpha\cos 2\alpha$, поэтому левая часть равна $\sin 3\alpha(2\cos 2\alpha + 1) = 3\sin 3\alpha$" + NOT, r"$2\cos 2\alpha + 1$ зависит от $\alpha$ и не равно $3$; оно равно $\dfrac{\sin 3\alpha}{\sin\alpha}$."),
       (r"$\sin\alpha + \sin 3\alpha + \sin 5\alpha = \sin 9\alpha$" + NOT, SUMF),
       (r"Левая часть равна $\sin 3\alpha(1 + 2\cos 2\alpha)$, а $1 + 2\cos 2\alpha = \dfrac{\sin\alpha}{\sin 3\alpha}$, поэтому она равна $\sin\alpha$" + NOT, r"$\sin 3\alpha = \sin\alpha(3 - 4\sin^{2}\alpha) = \sin\alpha(1 + 2\cos 2\alpha)$, т. е. $1 + 2\cos 2\alpha = \dfrac{\sin 3\alpha}{\sin\alpha}$.")]},
"ds_llm_832484e86455": {
 "k": r"$\operatorname{tg}\alpha \pm \operatorname{ctg}\alpha = \dfrac{\sin^{2}\alpha \pm \cos^{2}\alpha}{\sin\alpha\cos\alpha}$, поэтому дробь равна $\dfrac{\sin^{2}\alpha + \cos^{2}\alpha}{\sin^{2}\alpha - \cos^{2}\alpha}$.",
 "d": [(r"$\operatorname{tg}\alpha + \operatorname{ctg}\alpha = 1$, поэтому дробь равна $\dfrac{1}{\operatorname{tg}\alpha - \operatorname{ctg}\alpha}$" + NOT, r"$\operatorname{tg}\alpha \cdot \operatorname{ctg}\alpha = 1$, а сумма $\operatorname{tg}\alpha + \operatorname{ctg}\alpha = \dfrac{1}{\sin\alpha\cos\alpha}$."),
       (r"Дробь равна $\dfrac{\sin^{2}\alpha + \cos^{2}\alpha}{\cos^{2}\alpha - \sin^{2}\alpha}$" + NOT, r"$\operatorname{tg}\alpha - \operatorname{ctg}\alpha = \dfrac{\sin^{2}\alpha - \cos^{2}\alpha}{\sin\alpha\cos\alpha}$: порядок вычитания перепутан."),
       (r"Числитель и знаменатель после сокращения равны $1$ и $-1$, поэтому дробь равна $-1$" + NOT, r"Сокращать слагаемые нельзя; числитель и знаменатель приводят к общему знаменателю $\sin\alpha\cos\alpha$.")]},
"ds_llm_8cbfd0ad83a3": {
 "d": [(r"$a = -6$, так как $(-6)^{2} = 36$; точки симметричны, так как у них одинаковые ординаты.", r"По условию $a > 0$, поэтому $a = 6$."),
       (r"$a = 6\sqrt{2}$, так как $a^{2} = 72$; точки симметричны относительно оси $Oy$, так как $f(-x) = f(x)$.", r"$a^{2} = 36$, поэтому $a = 6$; число $72$ получено неверно."),
       (r"$a = 18$, так как $36 : 2 = 18$; точки симметричны относительно оси $Ox$.", r"$a^{2} = 36$, а не $2a = 36$; точки $(-a; y_{0})$ и $(a; y_{0})$ симметричны относительно оси $Oy$.")]},
"ds_llm_b9a2292b257a": {
 "d": [(r"$\sin 5\alpha + \sin 3\alpha = 2\sin 8\alpha\cos 2\alpha$" + NOT, r"В формуле берутся полусумма и полуразность: $4\alpha$ и $\alpha$."),
       (r"$\sin 5\alpha + \sin 3\alpha = 2\sin\alpha\cos 4\alpha$" + NOT, r"Для суммы синусов синус берётся от полусуммы: $2\sin 4\alpha\cos\alpha$."),
       (r"$\sin 5\alpha + \sin 3\alpha = \sin 8\alpha = 2\sin 4\alpha\cos 4\alpha$" + NOT, SUMF)]},
"ds_llm_d776c3e6bd01": {
 "k": r"$\dfrac{\sin\alpha}{1 + \cos\alpha} + \dfrac{1 + \cos\alpha}{\sin\alpha} = \dfrac{\sin^{2}\alpha + 1 + 2\cos\alpha + \cos^{2}\alpha}{\sin\alpha(1 + \cos\alpha)} = \dfrac{2(1 + \cos\alpha)}{\sin\alpha(1 + \cos\alpha)} = \dfrac{2}{\sin\alpha}$.",
 "d": [(r"Числитель $\sin^{2}\alpha + (1 + \cos\alpha)^{2} = 2$, поэтому левая часть равна $\dfrac{2}{\sin\alpha(1 + \cos\alpha)}$" + NOT, r"$(1 + \cos\alpha)^{2} = 1 + 2\cos\alpha + \cos^{2}\alpha$: удвоенное произведение потеряно."),
       (r"Числитель равен $2(1 + \cos\alpha)$, поэтому левая часть равна $\dfrac{2}{1 + \cos\alpha}$" + NOT, r"Сокращается множитель $1 + \cos\alpha$, и остаётся $\dfrac{2}{\sin\alpha}$."),
       (r"$\dfrac{\sin\alpha}{1 + \cos\alpha} + \dfrac{1 + \cos\alpha}{\sin\alpha} = \dfrac{\sin\alpha + 1 + \cos\alpha}{1 + \cos\alpha + \sin\alpha} = 1$" + NOT, r"Дроби складывают через общий знаменатель.")]},
"ds_llm_ddf58bfd66ce": {
 "k": r"$\sin\alpha + \sin 7\alpha = 2\sin 4\alpha\cos 3\alpha$ и $\sin 3\alpha + \sin 5\alpha = 2\sin 4\alpha\cos\alpha$, поэтому сумма равна $2\sin 4\alpha(\cos 3\alpha + \cos\alpha) = 4\sin 4\alpha\cos 2\alpha\cos\alpha$.",
 "d": [(r"Сумма равна $2\sin 4\alpha(\cos 3\alpha + \cos\alpha) = 2\sin 4\alpha\cos 2\alpha\cos\alpha$" + NOT, r"$\cos 3\alpha + \cos\alpha = 2\cos 2\alpha\cos\alpha$: множитель $2$ потерян."),
       (r"$\sin\alpha + \sin 7\alpha = 2\sin 8\alpha\cos 6\alpha$, поэтому сумма не сводится к правой части" + NOT, r"В формуле берутся полусумма $4\alpha$ и полуразность $3\alpha$."),
       (r"$\sin\alpha + \sin 3\alpha + \sin 5\alpha + \sin 7\alpha = \sin 16\alpha$" + NOT, SUMF)]},
"ds_llm_f2bc9d40f858": {
 "d": [(r"$\sin 5\alpha - \sin 3\alpha = 2\cos\alpha\sin 4\alpha$" + NOT, r"В формуле разности синусов синус берётся от полуразности: $2\sin\alpha\cos 4\alpha$."),
       (r"$\sin 5\alpha - \sin 3\alpha = \sin 2\alpha = 2\sin\alpha\cos\alpha$" + NOT, r"Разность синусов не равна синусу разности углов."),
       (r"$\sin 5\alpha - \sin 3\alpha = 2\sin 4\alpha\cos\alpha$" + NOT, r"Это формула суммы синусов; для разности $2\sin\dfrac{x - y}{2}\cos\dfrac{x + y}{2}$.")]},
}
