import sys; sys.path.insert(0, "/audit")
import re, json, importlib.util, psycopg2
from fractions import Fraction as F
from math import cos, pi
spec = importlib.util.spec_from_file_location("c", "/audit/fix_v5f.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
def num(k): return F(re.sub(r"[\s$]", "", k).replace("{,}", ".").replace(",", ".").replace("\\,", ""))
calc = {"G6_TB_37_1369.1": F("12") + F("7.8") * (F("8.1") - F("8.4")), "G6_TB_37_1369.2": -6 - F("4.5") * (F("5.2") - F("10.6")), "G8_ALG_8_111.2": 2 - F("0.5") * (-6),
        "G5_TB_34_1318.6": 2 - F("0.6"), "G5_TB_34_1318.3": 3 + F("0.24"), "G5_TB_33_1293.3": 504 - F("47.9") + (F("58.7") - 49), "G5_TB_32_1219.6": 425 - F("2.647"),
        "G5_TB_32_1219.4": 129 + F("9.72"), "G5_TB_33_1256.5": 15 - F("1.12"), "G7_ALG_6_7.3": F("5.567") * 1000, "G7_TB_32_826.4": F("9.9") ** 2,
        "G9_TB_13_206_3": 2 * F("-0.3") ** 2 + F("1.2") * F("-0.3") + 2}
for t, (a, b) in {"G5_TB_64_1521.%d" % i: v for i, v in zip([1, 2, 3, 5, 6, 7, 8], [(29, "4.3"), ("2.9", 43), ("2.9", "0.43"), ("2.9", "0.0043"), ("2.9", 430), ("0.29", "0.43"), (290, "4.3")])}.items(): calc[t] = F(str(a)) * F(str(b))
for t, (a, b) in {"G5_TB_64_1528.%d" % i: v for i, v in zip([1, 2, 3, 5, 6, 7, 8], [(89, "7.3"), ("8.9", 73), ("8.9", "0.73"), ("8.9", "0.0073"), (89, "0.73"), ("0.89", "0.73"), (890, "7.3")])}.items(): calc[t] = F(str(a)) * F(str(b))
bad = []
for t, v in calc.items():
    c.execute("SELECT correct_answer_latex FROM tasks_master WHERE id=%s", (t,)); k = c.fetchone()[0]
    kk = F(81, 25) if "dfrac{81}" in k else num(k.split("[")[-1].split(";")[0]) if t == "G9_TB_13_206_3" else num(k)
    if kk != v: bad.append((t, k, v))
# y_n: 1.5, 2.5, 4.5, 7.5, 11.5
y = [F("1.5")]; [y.append(y[-1] + n) for n in range(1, 5)]; assert y == [F(x) for x in ("1.5", "2.5", "4.5", "7.5", "11.5")]
assert cos(20 * pi / 180) > cos(5.1) and 5 * 1.5 > 2 * (1.5 - 1) + 6 and 3.2 ** (-2 ** .5) < 1 and (3 / 5) ** (-3 ** .5 / 2) > 1 and 0.7 ** (5 ** .5 / 9) < 0.7 ** (1 / 6) and 5 ** (-13 ** .5) < 0.2 ** 2.1
assert [x for x in range(0, 9) if 0 <= x <= 7.2] == list(range(8))
print("checked", len(calc) + 8, "bad", bad)
