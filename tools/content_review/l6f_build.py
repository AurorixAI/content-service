# -*- coding: utf-8 -*-
import json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
KEY23 = r"Общий вид: $z = r(\cos\varphi + i\sin\varphi)$, где $r = |z|$, $\varphi = \arg z$. Примеры: $z_{1} = 2\left(\cos\dfrac{\pi}{3} + i\sin\dfrac{\pi}{3}\right)$, $z_{2} = \sqrt{2}\left(\cos\dfrac{3\pi}{4} + i\sin\dfrac{3\pi}{4}\right)$."
FIX = {
 "G11_TB_2_3": {"correct_answer_latex": KEY23, "opt": {0: KEY23}, "why": "в отображении ключа: √2 → \\sqrt{2}, z1 → z_{1}, argz → \\arg z, π/3 → дробь"},
 "G11_TB_§4_1_1": {"opt": {3: r"$\sin 2x + \dfrac{\sqrt{2}}{2\sqrt{x}}$"}, "why": "вариант 4 был искажён («√\\dfrac{2}{2√x}»); запись восстановлена по сырому значению: sin 2x + √2/(2√x)"},
 "G9_TB_21_252_1": {"opt": {1: r"$x = -\dfrac{3\pi}{2} + 2\pi k, k \in \mathbb{Z}$", 3: r"$x = -\dfrac{3\pi}{2} + \pi k, k \in \mathbb{Z}$"},
                    "dm": {"x = π/2 + 2πk, k ∈ Z": r"$x = \dfrac{\pi}{2} + 2\pi k, k \in \mathbb{Z}$", "x = π/10 + 2πk/5, k ∈ Z": r"$x = \dfrac{\pi}{10} + \dfrac{2\pi k}{5}, k \in \mathbb{Z}$"},
                    "why": "формулы были записаны текстом без $…$ и через «/»"},
 "ds_llm_067731103040": {"dm": {"x ∈ ∅ (нет решений)": r"$x \in \varnothing$ (нет решений)"}, "why": "формула была текстом без $…$"},
 "ds_llm_94d9574168be": {"dm": {"a^(-2)": r"$a^{-2}$"}, "why": "запись «a^(-2)» в стиле кода"},
 "ds_llm_ff48767c27ac": {"dm": {r"$\dfrac{\cos_{a}}{\sqrt{1 - \cos_{a}^{2}}}$": r"$\dfrac{\cos\alpha}{\sqrt{1 - \cos^{2}\alpha}}$",
                               r"$\dfrac{\sqrt{1 - \cos^{2} a}}{\cos a}$": r"$\dfrac{\sqrt{1 - \cos^{2}\alpha}}{\cos\alpha}$",
                               r"$\dfrac{- \sqrt{1 - cos_{a}^{2}}}{cos_{a}}$": r"$-\dfrac{\sqrt{1 - \cos^{2}\alpha}}{\cos\alpha}$"},
                         "why": "«cos_{a}» (индекс вместо аргумента) и переменная a вместо α — приведено к записи условия"},
}
c.execute("SELECT id, answer_options_latex, distractor_meta FROM tasks_master WHERE id = ANY(%s)", (list(FIX),))
spec = {}
for tid, aol, dm in c.fetchall():
    fx = FIX[tid]; f = {}
    if "correct_answer_latex" in fx: f["correct_answer_latex"] = fx["correct_answer_latex"]
    if "opt" in fx:
        new = list(aol)
        for i, v in fx["opt"].items():
            new[i] = dict(new[i], text=v) if isinstance(new[i], dict) else v
        f["answer_options_latex"] = new
    if "dm" in fx:
        hit = 0; new = []
        for d in dm:
            if isinstance(d, dict) and d.get("value") in fx["dm"]:
                new.append(dict(d, value_latex=fx["dm"][d["value"]])); hit += 1
            else: new.append(d)
        assert hit == len(fx["dm"]), (tid, hit)
        f["distractor_meta"] = new
    spec[tid] = {"why": "ручная правка отображения (LaTeX), сверено с сырым значением: " + fx["why"], "source": "L6f, 25.09", "fields": f, "latex_display_manual": True}
json.dump(spec, open("/audit/restore_J_L6f.json", "w"), ensure_ascii=False, indent=1)
print(len(spec))
