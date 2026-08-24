import psycopg2
import json

conn = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="localhost", port=5434)
cur = conn.cursor()

# 1. ds_llm_7c36694c8cba (Asymptotes & Convexity)
dm_7c = [
    {
        "value": "Горизонтальная асимптота $y=-1$; выпукла вверх на $(-1$, $1)$, выпукла вниз на $(-\\infty$, $-1)\\cup(1$, $+\\infty)$; точки перегиба $(-1$, $0)$ и $(1$, $0)$.",
        "value_latex": "Горизонтальная асимптота $y=-1$; выпукла вверх на $(-1, 1)$, выпукла вниз на $(-\\infty, -1)\\cup(1, +\\infty)$; точки перегиба $(-1, 0)$ и $(1, 0)$",
        "error_type": "conceptual",
        "explanation": "Ученик неверно нашёл предел при $x \\to \\infty$, посчитав $\\lim \\frac{x^2-1}{x^2+1} = -1$ вместо $1$. Также вместо корней второй производной $f''(x)=0$ для точек перегиба он ошибочно взял нули самой функции ($x = \\pm 1$)."
    },
    {
        "value": "Горизонтальная асимптота $y=1$; выпукла вниз на $(-\\infty$, $0)$, выпукла вверх на $(0$, $+\\infty)$; точка перегиба $(0$, $-1)$.",
        "value_latex": "Горизонтальная асимптота $y=1$; выпукла вниз на $(-\\infty, 0)$, выпукла вверх на $(0, +\\infty)$; точка перегиба $(0, -1)$",
        "error_type": "derivative_confusion",
        "explanation": "Ученик перепутал первую и вторую производные: точка $x=0$ является точкой локального минимума ($f'(0)=0$), а не точкой перегиба, так как вторая производная в нуле знак не меняет."
    },
    {
        "value": "Горизонтальная асимптота $y=0$; выпукла вверх на всей области определения; точек перегиба нет.",
        "value_latex": "Горизонтальная асимптота $y=0$; выпукла вверх на всей области определения; точек перегиба нет",
        "error_type": "conceptual",
        "explanation": "Ученик посчитал, что любая дробно-рациональная функция имеет горизонтальную асимптоту $y=0$, и не исследовал знак второй производной функции."
    }
]

# 2. G11_TB_17_2_17_2_1 (Log inequality)
dm_log = [
    {
        "value": "$(8; +\\infty)$",
        "value_latex": "$(8; +\\infty)$",
        "error_type": "algebraic",
        "explanation": "Ученик вместо потенцирования $2^3 = 8$ выполнил $x - 5 > 3 \\implies x > 8$, полностью забыв раскрыть логарифм."
    },
    {
        "value": "$(5; 13)$",
        "value_latex": "$(5; 13)$",
        "error_type": "inequality_direction",
        "explanation": "Ученик изменил знак неравенства на противоположный ($x - 5 < 8 \\implies x < 13$) и ограничил снизу областью допустимых значений $x > 5$."
    },
    {
        "value": "$(13; +\\infty) \\cup (-\\infty; 5)$",
        "value_latex": "$(13; +\\infty) \\cup (-\\infty; 5)$",
        "error_type": "domain_misconception",
        "explanation": "Ученик ошибочно объединил решение $x > 13$ с областью, где подлогарифмическое выражение отрицательно ($x < 5$), нарушив ОДЗ."
    }
]

# 3. ds_llm_c0496647fb8f (Inverse function)
dm_inv = [
    {
        "value": "$y = 2 \\pm \\sqrt{x - 1}, x \\in [1; +\\infty)$",
        "value_latex": "$y = 2 \\pm \\sqrt{x - 1}, x \\in [1; +\\infty)$",
        "error_type": "function_definition",
        "explanation": "Ученик оставил знак $\\pm$, забыв, что обратная функция должна быть однозначной. Для заданного промежутка $[2; +\\infty)$ выбирается единственная ветвь со знаком плюс: $y = 2 + \\sqrt{x-1}$."
    },
    {
        "value": "$y = 2 - \\sqrt{x - 1}, x \\in [1; +\\infty)$",
        "value_latex": "$y = 2 - \\sqrt{x - 1}, x \\in [1; +\\infty)$",
        "error_type": "branch_choice",
        "explanation": "Ученик выбрал левую ветвь параболы (знак минус), соответствующую промежутку $(-\\infty; 2]$, в то время как исходная функция рассматривается на $[2; +\\infty)$."
    },
    {
        "value": "$y = 2 + \\sqrt{x - 1}, x \\in [0; +\\infty)$",
        "value_latex": "$y = 2 + \\sqrt{x - 1}, x \\in [0; +\\infty)$",
        "error_type": "domain_error",
        "explanation": "Ученик допустил ошибку в области определения обратной функции, забыв, что подкоренное выражение требует $x - 1 \\ge 0 \\implies x \\in [1; +\\infty)$."
    }
]

# 4. ds_llm_597893f5514d (Trig transformation)
dm_trig = [
    {
        "value": "$y = 2\\sin\\left(3x - \\frac{\\pi}{6}\\right) - 1, T = \\frac{2\\pi}{3}$",
        "value_latex": "$y = 2\\sin\\left(3x - \\dfrac{\\pi}{6}\\right) - 1, T = \\dfrac{2\\pi}{3}$",
        "error_type": "transformation_order",
        "explanation": "Ученик применил сжатие вдоль оси Ox в 3 раза, записав $\\sin(3x)$, затем сдвиг вправо на $\\frac{\\pi}{6}$, записав $\\sin\\left(3x - \\frac{\\pi}{6}\\right)$, забыв, что сдвиг применяется непосредственно к аргументу $x$: $\\sin\\left(3\\left(x - \\frac{\\pi}{6}\\right)\\right) = \\sin\\left(3x - \\frac{\\pi}{2}\\right)$."
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
        "explanation": "Ученик перепутал сжатие и растяжение: при сжатии вдоль оси Ox в 3 раза аргумент умножается на 3 ($\\sin 3x$), а не делится на 3."
    }
]

# 5. G11_TB_§4_6_2 (Product rule derivative)
dm_prod = [
    {
        "value": "$3x^{2} * cos x$",
        "value_latex": "$3x^{2} \\cos x$",
        "error_type": "product_rule",
        "explanation": "Ученик перемножил производные сомножителей $(x^3)' \\cdot (\\sin x)' = 3x^2 \\cos x$ вместо применения правила дифференцирования произведения $(uv)' = u'v + uv'$."
    },
    {
        "value": "$x^{3} * cos x$",
        "value_latex": "$x^{3} \\cos x$",
        "error_type": "product_rule",
        "explanation": "Ученик продифференцировал только второй сомножитель $\\sin x$, оставив первый $x^3$ без изменений и не добавив второе слагаемое."
    },
    {
        "value": "$3x^{2} * sin x$",
        "value_latex": "$3x^{2} \\sin x$",
        "error_type": "product_rule",
        "explanation": "Ученик продифференцировал только первый сомножитель $x^3$, проигнорировав дифференцирование второго."
    }
]

# 6. G11_TB_§4_3_1 (Quotient rule derivative)
dm_quot = [
    {
        "value": "$\\cos x$",
        "value_latex": "$\\cos x$",
        "error_type": "quotient_rule",
        "explanation": "Ученик продифференцировал числитель $(\\sin x)' = \\cos x$ и знаменатель $(x)' = 1$ по отдельности: $\\frac{\\cos x}{1} = \\cos x$, вместо применения формулы производной частного."
    },
    {
        "value": "$\\dfrac{\\cos x - \\sin x}{x^{2}}$",
        "value_latex": "$\\dfrac{\\cos x - \\sin x}{x^{2}}$",
        "error_type": "quotient_rule",
        "explanation": "Ученик забыл умножить производную числителя на знаменатель $x$, получив в числителе $\\cos x - \\sin x$ вместо $x\\cos x - \\sin x$."
    },
    {
        "value": "$-\\dfrac{\\cos x}{x^{2}}$",
        "value_latex": "$-\\dfrac{\\cos x}{x^{2}}$",
        "error_type": "quotient_rule",
        "explanation": "Ученик применил правило для функции $1/x$, продифференцировав числитель и добавив минус перед дробью."
    }
]

# 7. ds_llm_cd5434919101 (Local extremum)
dm_ext = [
    {
        "value": "$x_{\\min} = 0, f(0) = 4$",
        "value_latex": "$x_{\\min} = 0, f(0) = 4$",
        "error_type": "conceptual",
        "explanation": "Ученик спутал точку минимума с точкой пересечения графика с осью ординат (подставил $x=0$) вместо нахождения корней производной $f'(x)=0$."
    },
    {
        "value": "$x_{\\min} = -2, f(-2) = 16$",
        "value_latex": "$x_{\\min} = -2, f(-2) = 16$",
        "error_type": "sign_error",
        "explanation": "Ученик ошибся в знаке при решении уравнения $f'(x) = 2x - 4 = 0$, получив $x = -2$ вместо $x = 2$."
    },
    {
        "value": "$x_{\\max} = 2, f(2) = 0$",
        "value_latex": "$x_{\\max} = 2, f(2) = 0$",
        "error_type": "extremum_type",
        "explanation": "Ученик верно нашёл стационарную точку $x = 2$, но перепутал тип экстремума, назвав минимум максимумом."
    }
]

updates = [
    ("ds_llm_7c36694c8cba", dm_7c),
    ("G11_TB_17_2_17_2_1", dm_log),
    ("ds_llm_c0496647fb8f", dm_inv),
    ("ds_llm_597893f5514d", dm_trig),
    ("G11_TB_§4_6_2", dm_prod),
    ("G11_TB_§4_3_1", dm_quot),
    ("ds_llm_cd5434919101", dm_ext)
]

for tid, dm in updates:
    cur.execute("UPDATE tasks_master SET distractor_meta = %s::jsonb WHERE id = %s;", (json.dumps(dm, ensure_ascii=False), tid))

conn.commit()
print("Updated all 7 tasks successfully!")
conn.close()
