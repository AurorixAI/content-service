# -*- coding: utf-8 -*-
# Keys refuted by two independent sources (25.09): the statement evaluated numerically AND the textbook answer section
# agree with each other and disagree with the key (cross_check.py verdict key_wrong_book_confirms). Key := book answer.
M = "Мерзляк 10"; A = "Алимов 9"; K = "Макарычев 9"
N = {
 "G10_TB_§20_20_8_5": (r"$\operatorname{tg}^{2}\alpha$", M, "20.8 (5)"),
 "G10_TB_§20_20_8_7": (r"$-1$", M, "20.8 (7)"),
 "G10_TB_§21_21_21_1": (r"$\operatorname{ctg}\dfrac{\alpha}{4}$", M, "21.21 (1)"),
 "G10_TB_§21_21_3_8": (r"$\operatorname{tg} 15^{\circ}$", M, "21.3 (8)"),
 "G10_TB_§22_22_9_1": (r"$-\cos\alpha$", M, "22.9 (1)"),
 "G10_TB_§22_22_9_6": (r"$1$", M, "22.9 (6)"),
 "G10_TB_§23_22_15_1": (r"$\cos^{2}\alpha$", M, "22.15 (1)"),
 "G10_TB_§23_23_34_1": (r"$\dfrac{1}{4}$", M, "23.34 (1)"),
 "G10_TB_§23_23_34_3": (r"$-\dfrac{1}{4}\sin^{2}\alpha$", M, "23.34 (3)"),
 "G10_TB_§23_23_4_7": (r"$2\sin 2\alpha$", M, "23.4 (7)"),
 "G10_TB_§24_24_14": (r"$8\sqrt[3]{2}$", M, "24.14"),
 "G10_TB_§24_24_4_1": (r"$\dfrac{\cos\alpha}{\cos 4\alpha}$", M, "24.4 (1)"),
 "G10_TB_§24_24_7_1": (r"$4\sin\left(\dfrac{\alpha}{2} + \dfrac{\pi}{6}\right)\sin\left(\dfrac{\alpha}{2} - \dfrac{\pi}{6}\right)$", M, "24.7 (1)"),
 "G10_TB_§42_42_39_4": (r"$2\operatorname{tg}^{2}\alpha$", M, "42.39 (4)"),
 "G10_TB_§8_8_9_1": (r"$-11{,}8$", M, "8.9 (1)"),
 "G10_TB_§9_8_37_1": (r"$m^{4}\sqrt{-m}$", M, "8.37 (1)"),
 "G10_TB_§9_9_18_6": (r"$\sqrt[3]{a}$", M, "9.18 (6)"),
 "G10_TB_§9_9_45_2": (r"$\sqrt[6]{x}$", M, "9.45 (2)"),
 "G10_TB_§9_9_45_3": (r"$-\sqrt[4]{a}$", M, "9.45 (3)"),
 "G10_TB_§9_9_45_4": (r"$\sqrt[6]{a}$", M, "9.45 (4)"),
 "G9_TB_24_276_2": (r"$2\cos\alpha$", A, "276 (2)"),
 "G9_TB_24_279_2": (r"$-2\cos\alpha$", A, "279 (2)"),
 "G9_TB_26_312_2": (r"$\cos 2\alpha$", A, "312 (2)"),
 "G9_TB_26_313_4": (r"$\dfrac{1}{2}$", A, "313 (4)"),
 "G9_TB_ДГ5_681_2": (r"$\dfrac{5}{6}$", K, "681 б)"),
 "G9_TB_УКГ3_325_2": (r"$2\sqrt{3}\sin\dfrac{5\pi}{24}\sin\dfrac{\pi}{8}$", A, "325 (2)"),
 "G9_TB_УКГ3_345_2": (r"$\dfrac{1}{\sin 4\alpha}$", A, "345 (2)"),
 "G9_TB_УПК_687_2": (r"$\dfrac{2\sqrt{2}}{3}$", K, "687 б)"),
 "G9_TB_УПК_710_в": (r"$\dfrac{2}{x+2}$", K, "710 в)"),
}
P = {t: {"k": k, "why": f"ключ неверен: выражение из условия, вычисленное численно, совпадает с ответом учебника ({b}, № {n}) и не совпадает с прежним ключом; ключ заменён ответом учебника",
         "src": f"{b}: раздел ответов; численная проверка 25.09"} for t, (k, b, n) in N.items()}
