# -*- coding: utf-8 -*-
# Owner decision 2026-09-25: textbook misprints are corrected by meaning (not left deactivated).
# Alimov 9 №291(3): denominator 2sin(π/4 + α) → 2sin(π/6 + α) — with it the identity holds (checked numerically at 4 points).
# Nelin 11 §24 ex. 1.4: F(x) = (1/6)x^6 → F(x) = −(1/6)x^{−6} — the antiderivative of x^{−7} (checked numerically).
NOT = r", поэтому тождество неверно."
NOTF = r", поэтому $F$ не является первообразной для $f$ на $(0; +\infty)$."
P = {
"G9_TB_25_291_3": {
 "q": r"Докажите тождество: $\dfrac{\sqrt{2}\cos\alpha - 2\cos\left(\dfrac{\pi}{4} - \alpha\right)}{2\sin\left(\dfrac{\pi}{6} + \alpha\right) - \sqrt{3}\sin\alpha} = -\sqrt{2}\operatorname{tg}\alpha$",
 "qwhy": "в учебнике опечатка (Алимов 9, с. 126, № 291 (3)): при 2sin(π/4 + α) в знаменателе тождество неверно; по решению владельца условие исправлено по смыслу — в знаменателе 2sin(π/6 + α), тогда тождество верно",
 "src": "исправление опечатки учебника по решению владельца 25.09; тождество проверено численно",
 "k": r"Числитель $\sqrt{2}\cos\alpha - 2\left(\dfrac{\sqrt{2}}{2}\cos\alpha + \dfrac{\sqrt{2}}{2}\sin\alpha\right) = -\sqrt{2}\sin\alpha$, знаменатель $2\left(\dfrac{1}{2}\cos\alpha + \dfrac{\sqrt{3}}{2}\sin\alpha\right) - \sqrt{3}\sin\alpha = \cos\alpha$, поэтому дробь равна $-\sqrt{2}\operatorname{tg}\alpha$.",
 "d": [(r"Числитель $\sqrt{2}\cos\alpha - 2\left(\dfrac{\sqrt{2}}{2}\cos\alpha - \dfrac{\sqrt{2}}{2}\sin\alpha\right) = \sqrt{2}\sin\alpha$, знаменатель $\cos\alpha$, поэтому дробь равна $\sqrt{2}\operatorname{tg}\alpha$" + NOT, r"$\cos\left(\dfrac{\pi}{4} - \alpha\right) = \cos\dfrac{\pi}{4}\cos\alpha + \sin\dfrac{\pi}{4}\sin\alpha$: в косинусе разности знак «+»."),
       (r"Знаменатель $2\left(\dfrac{\sqrt{3}}{2}\cos\alpha + \dfrac{1}{2}\sin\alpha\right) - \sqrt{3}\sin\alpha$ не сводится к $\cos\alpha$" + NOT, r"$\sin\dfrac{\pi}{6} = \dfrac{1}{2}$, $\cos\dfrac{\pi}{6} = \dfrac{\sqrt{3}}{2}$: значения перепутаны; верно $\sin\left(\dfrac{\pi}{6} + \alpha\right) = \dfrac{1}{2}\cos\alpha + \dfrac{\sqrt{3}}{2}\sin\alpha$."),
       (r"Числитель равен $-\sqrt{2}\sin\alpha$, знаменатель $\cos\alpha$, поэтому дробь равна $-\sqrt{2}\operatorname{ctg}\alpha$" + NOT, r"$\dfrac{\sin\alpha}{\cos\alpha} = \operatorname{tg}\alpha$.")]},
"G11_TB_§24_1_4": {
 "q": r"Докажите, что функция $F(x)$ — первообразная для функции $f(x)$ на указанном промежутке: $F(x) = -\dfrac{1}{6}x^{-6}$, $f(x) = x^{-7}$, $x \in (0; +\infty)$",
 "qwhy": "в учебнике опечатка (Нелин 11, с. 357, упр. 1.4): F(x) = x⁶/6 не является первообразной для x⁻⁷; по решению владельца условие исправлено по смыслу — F(x) = −x⁻⁶/6",
 "src": "исправление опечатки учебника по решению владельца 25.09; производная проверена",
 "k": r"$F'(x) = -\dfrac{1}{6} \cdot (-6)x^{-7} = x^{-7} = f(x)$ при всех $x \in (0; +\infty)$, поэтому $F$ — первообразная для $f$ на этом промежутке.",
 "d": [(r"$F'(x) = -\dfrac{1}{6} \cdot (-6)x^{-5} = x^{-5} \ne f(x)$" + NOTF, r"При дифференцировании показатель уменьшается на $1$: $(x^{-6})' = -6x^{-7}$."),
       (r"$F'(x) = -\dfrac{1}{6} \cdot 6x^{-7} = -x^{-7} \ne f(x)$" + NOTF, r"$(x^{-6})' = -6x^{-7}$: знак «−» показателя потерян, и минусы не сократились."),
       (r"$F'(x) = -\dfrac{1}{6} \cdot \dfrac{x^{-5}}{-5} = \dfrac{x^{-5}}{30} \ne f(x)$" + NOTF, r"Вместо производной найдена первообразная; нужно $(x^{n})' = nx^{n-1}$.")]},
}
