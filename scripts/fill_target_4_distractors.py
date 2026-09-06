import psycopg2
import json

conn = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="localhost", port=5434)
cur = conn.cursor()

# 1. G11_TB_5_10*_5_100
dm_100 = [
    {
        "value": "Горизонтальная асимптота $y = -1$; выпукла вверх на $(-1, 1)$, выпукла вниз на $(-\\infty, -1) \\cup (1, +\\infty)$; точки перегиба $(-1,0)$ и $(1,0)$",
        "value_latex": "Горизонтальная асимптота $y = -1$; выпукла вверх на $(-1, 1)$, выпукла вниз на $(-\\infty, -1) \\cup (1, +\\infty)$; точки перегиба $(-1,0)$ и $(1,0)$",
        "error_type": "conceptual",
        "explanation": "Ученик неверно нашёл предел при $x \\to \\infty$, посчитав предел равным $-1$ вместо $1$. Также вместо корней второй производной для точек перегиба он ошибочно взял нули самой функции ($x = \\pm 1$)."
    },
    {
        "value": "Горизонтальная асимптота $y = 1$; выпукла вниз на $(-\\infty,0)$, выпукла вверх на $(0,+\\infty)$; точка перегиба $(0,-1)$",
        "value_latex": "Горизонтальная асимптота $y = 1$; выпукла вниз на $(-\\infty,0)$, выпукла вверх на $(0,+\\infty)$; точка перегиба $(0,-1)$",
        "error_type": "derivative_confusion",
        "explanation": "Ученик перепутал первую и вторую производные: точка $x=0$ является точкой минимума ($f'(0)=0$), а не точкой перегиба, так как вторая производная в нуле не меняет знак."
    },
    {
        "value": "Горизонтальная асимптота $y = 0$; выпукла вверх на всей области определения; точек перегиба нет",
        "value_latex": "Горизонтальная асимптота $y = 0$; выпукла вверх на всей области определения; точек перегиба нет",
        "error_type": "conceptual",
        "explanation": "Ученик решил, что горизонтальная асимптота всегда $y=0$, и не исследовал знак второй производной функции."
    }
]

# 2. ds_llm_e0bf6bc0297f
dm_log = [
    {
        "value": "(8; +\\infty)",
        "value_latex": "(8; +\\infty)",
        "error_type": "algebraic",
        "explanation": "Ученик вместо возведения основания в степень $2^3 = 8$ выполнил $x - 5 > 3 \\implies x > 8$, полностью забыв раскрыть логарифм."
    },
    {
        "value": "(5; 13)",
        "value_latex": "(5; 13)",
        "error_type": "inequality_direction",
        "explanation": "Ученик перепутал знак неравенства с противоположным ($x - 5 < 8 \\implies x < 13$) и ограничил снизу областью определения $x > 5$."
    },
    {
        "value": "(13; +\\infty) \\cup (-\\infty; 5)",
        "value_latex": "(13; +\\infty) \\cup (-\\infty; 5)",
        "error_type": "domain_misconception",
        "explanation": "Ученик ошибочно включил в ответ область, где подлогарифмическое выражение отрицательно ($x < 5$), нарушив ОДЗ."
    }
]

# 3. ds_llm_0da0eb59a11a
dm_inv = [
    {
        "value": "y = 2 \\pm \\sqrt{x-1}, x \\in [1; +\\infty)",
        "value_latex": "$y = 2 \\pm \\sqrt{x-1}, x \\in [1; +\\infty)$",
        "error_type": "function_definition",
        "explanation": "Ученик оставил знак $\\pm$, забыв, что обратная функция должна быть однозначной, и для промежутка $[2; +\\infty)$ выбирается ветвь со знаком плюс: $y = 2 + \\sqrt{x-1}$."
    },
    {
        "value": "y = 2 - \\sqrt{x-1}, x \\in [1; +\\infty)",
        "value_latex": "$y = 2 - \\sqrt{x-1}, x \\in [1; +\\infty)$",
        "error_type": "branch_choice",
        "explanation": "Ученик выбрал левую ветвь параболы (знак минус), которая соответствует промежутку $(-\\infty; 2]$, в то время как в условии задан промежуток $[2; +\\infty)$."
    },
    {
        "value": "y = 2 + \\sqrt{x-1}, x \\in [0; +\\infty)",
        "value_latex": "$y = 2 + \\sqrt{x-1}, x \\in [0; +\\infty)$",
        "error_type": "domain_error",
        "explanation": "Ученик допустил ошибку в области определения обратной функции, забыв, что подкоренное выражение $x - 1 \\ge 0 \\implies x \\in [1; +\\infty)$."
    }
]

# 4. ds_llm_597893f5514d
dm_trig = [
    {
        "value": "$y = 2\\sin\\left(3x - \\frac{\\pi}{6}\\right) - 1, T = \\frac{2\\pi}{3}$",
        "value_latex": "$y = 2\\sin\\left(3x - \\dfrac{\\pi}{6}\\right) - 1, T = \\dfrac{2\\pi}{3}$",
        "error_type": "transformation_order",
        "explanation": "Ученик применил сжатие вдоль оси Ox в 3 раза, записав $\\sin(3x)$, затем сдвиг вправо на $\\frac{\\pi}{6}$, записав $\\sin\\left(3x - \\frac{\\pi}{6}\\right)$, забыв, что сдвиг применяется к аргументу $x$: $\\sin\\left(3\\left(x - \\frac{\\pi}{6}\\right)\\right) = \\sin\\left(3x - \\frac{\\pi}{2}\\right)$."
    },
    {
        "value": "$y = 2\\sin\\left(3x - \\frac{\\pi}{2}\\right) - 1, T = \\frac{\\pi}{3}$",
        "value_latex": "$y = 2\\sin\\left(3x - \\dfrac{\\pi}{2}\\right) - 1, T = \\dfrac{\\pi}{3}$",
        "error_type": "period_calculation",
        "explanation": "Ученик верно получил формулу функции, но при нахождении периода ошибочно разделил $2\\pi$ на 3 и ещё раз на 2 (из-за вертикального растяжения). Период зависит только от коэффициента при $x$ ($T = \\frac{2\\pi}{k} = \\frac{2\\pi}{3}$)."
    },
    {
        "value": "$y = 2\\sin\\left(\\frac{x}{3} - \\frac{\\pi}{6}\\right) - 1, T = 6\\pi$",
        "value_latex": "$y = 2\\sin\\left(\\dfrac{x}{3} - \\dfrac{\\pi}{6}\\right) - 1, T = 6\\pi$",
        "error_type": "compression_vs_stretch",
        "explanation": "Ученик перепутал сжатие и растяжение: при сжатии в 3 раза аргумент умножается на 3 ($\\sin 3x$), а не делится."
    }
]

cur.execute("UPDATE tasks_master SET distractor_meta = %s::jsonb WHERE id = 'G11_TB_5_10*_5_100';", (json.dumps(dm_100, ensure_ascii=False),))
cur.execute("UPDATE tasks_master SET distractor_meta = %s::jsonb WHERE id = 'ds_llm_e0bf6bc0297f';", (json.dumps(dm_log, ensure_ascii=False),))
cur.execute("UPDATE tasks_master SET distractor_meta = %s::jsonb WHERE id = 'ds_llm_0da0eb59a11a';", (json.dumps(dm_inv, ensure_ascii=False),))
cur.execute("UPDATE tasks_master SET distractor_meta = %s::jsonb WHERE id = 'ds_llm_597893f5514d';", (json.dumps(dm_trig, ensure_ascii=False),))

conn.commit()
print("Successfully updated distractor_meta for all 4 target tasks!")
conn.close()
