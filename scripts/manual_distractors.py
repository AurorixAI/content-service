#!/usr/bin/env python3
"""Manually insert distractors for the 8 remaining Merzlyak tasks."""
import json
import os
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://algo:algo@content-postgres:5432/algo_content")

# Each entry: (task_id, list_of_distractor_dicts)
DISTRACTORS = [
    # G10_TB_§14_14_41: correct = π/4 (угол 45°)
    ("G10_TB_§14_14_41", [
        {"latex": r"$\frac{\pi}{3}$", "value": "pi/3", "reason": "Ошибочно подставляют 60° вместо 45°"},
        {"latex": r"$\frac{\pi}{6}$", "value": "pi/6", "reason": "Ошибочно подставляют 30° вместо 45°"},
        {"latex": r"$\frac{\pi}{2}$", "value": "pi/2", "reason": "Берут смежный угол (90°) вместо искомого"},
    ]),
    # G10_TB_§14_14_35: correct = π/6 (угол 30°)
    ("G10_TB_§14_14_35", [
        {"latex": r"$\frac{\pi}{4}$", "value": "pi/4", "reason": "Ошибочно подставляют 45° вместо 30°"},
        {"latex": r"$\frac{\pi}{3}$", "value": "pi/3", "reason": "Ошибочно подставляют 60° вместо 30°"},
        {"latex": r"$\frac{\pi}{12}$", "value": "pi/12", "reason": "Ошибка при составлении уравнения"},
    ]),
    # G10_TB_§9_9_20: correct = a + b
    ("G10_TB_§9_9_20", [
        {"latex": r"$a - b$", "value": "a - b", "reason": "Ошибка знака при раскрытии произведения"},
        {"latex": r"$ab$", "value": "ab", "reason": "Перемножают основания вместо упрощения"},
        {"latex": r"$\sqrt[6]{a} + \sqrt[6]{b}$", "value": "a^(1/6)+b^(1/6)", "reason": "Не завершают упрощение произведения разностью кубов"},
    ]),
    # G10_TB_§16_15_19_2: correct = [1/2; +∞) — область значений y=1/(sin x + 1)
    # sin x ∈ [-1; 1], sin x + 1 ∈ [0; 2], y = 1/(sin x+1) ∈ [1/2; +∞) (при sin x+1→0+ y→+∞, при sin x=1 y=1/2)
    ("G10_TB_§16_15_19_2", [
        {"latex": r"$(0; +\infty)$", "value": "(0; +inf)", "reason": "Забывают, что минимум знаменателя 1 (при sin x=1), не 0"},
        {"latex": r"$\left[\frac{1}{2}; 1\right]$", "value": "[1/2; 1]", "reason": "Не учитывают, что функция неограничена сверху при sin x→-1"},
        {"latex": r"$(0; 1]$", "value": "(0; 1]", "reason": "Путают область значений с областью значений самого sin x"},
    ]),
    # G10_TB_§26_26_4_2: correct = x = ±25π/6 + 10πn
    # cos(x/5) = -√3/2, x/5 = ±5π/6 + 2πn, x = ±25π/6 + 10πn
    ("G10_TB_§26_26_4_2", [
        {"latex": r"$x = \pm \frac{5\pi}{6} + 2\pi n, n \in \mathbb{Z}$", "value": "x=5pi/6+2pi*n", "reason": "Забывают умножить на 5 при переходе от x/5 к x"},
        {"latex": r"$x = \pm \frac{25\pi}{6} + 2\pi n, n \in \mathbb{Z}$", "value": "x=25pi/6+2pi*n", "reason": "Умножают 5 на числитель но не на период 2π"},
        {"latex": r"$x = \frac{25\pi}{6} + 10\pi n, n \in \mathbb{Z}$", "value": "x=25pi/6+10pi*n", "reason": "Теряют ±, берут только одну ветку арккосинуса"},
    ]),
    # G10_TB_§31_31_8_3: correct = 0; −5π/6·... (12 корней на [0;π] ≈ 0;−2.748...)
    # cos2x − cos4x = sin6x → много корней, дистракторы — типичные ошибки
    ("G10_TB_§31_31_8_3", [
        {"latex": r"$x = \frac{\pi n}{2}, n \in \mathbb{Z}$", "value": "pi*n/2", "reason": "Частичное решение: учитывают только тривиальные корни"},
        {"latex": r"$x = \frac{\pi n}{6}, n \in \mathbb{Z}$", "value": "pi*n/6", "reason": "Ошибка при применении формул суммы/разности косинусов"},
        {"latex": r"$x = \pi n, n \in \mathbb{Z}$", "value": "pi*n", "reason": "Учитывают только корни cos = 1 или cos = -1"},
    ]),
    # G10_TB_§31_31_6_3: correct = 0; 0.1309; 0.6545
    # 1 − cos8x = sin4x → типичные ошибки
    ("G10_TB_§31_31_6_3", [
        {"latex": r"$x = \frac{\pi n}{4}, n \in \mathbb{Z}$", "value": "pi*n/4", "reason": "Находят только тривиальные корни уравнения"},
        {"latex": r"$x = 0; \frac{\pi}{8}; \frac{3\pi}{8}$", "value": "0; pi/8; 3pi/8", "reason": "Ошибка при разложении на множители"},
        {"latex": r"$x = \frac{\pi n}{8}, n \in \mathbb{Z}$", "value": "pi*n/8", "reason": "Неверно применяют формулы двойного угла"},
    ]),
    # G10_TB_§31_31_5_2: correct = ±π/8; ±3π/24 ≈ ±0.3927; ±0.2618
    # 1 + cos8x = cos4x → типичные ошибки
    ("G10_TB_§31_31_5_2", [
        {"latex": r"$x = \pm \frac{\pi}{4} + \frac{\pi n}{2}, n \in \mathbb{Z}$", "value": "pi/4+pi*n/2", "reason": "Ошибочно упрощают до однородного уравнения"},
        {"latex": r"$x = \frac{\pi n}{4}, n \in \mathbb{Z}$", "value": "pi*n/4", "reason": "Находят только нули cosинуса, игнорируя ненулевые корни"},
        {"latex": r"$x = \pm\frac{\pi}{8} + \pi n, n \in \mathbb{Z}$", "value": "pi/8+pi*n", "reason": "Берут неполный набор периодических корней"},
    ]),
]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    ok = 0
    for tid, dlist in DISTRACTORS:
        cur.execute(
            "UPDATE tasks_master SET distractor_meta = %s WHERE id = %s",
            (json.dumps(dlist), tid)
        )
        print(f"  -> Updated {tid}: {len(dlist)} distractors")
        ok += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone. Updated {ok} tasks.")


if __name__ == "__main__":
    main()
