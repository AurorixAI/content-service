import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

clean_fixes = {
    'DIFF_G6_S32_03_C_02': [
        {
            "value": "минус",
            "value_latex": "\\text{минус}",
            "error_type": "ai_generated",
            "error_logic": "Ученик ошибся в подсчете количества отрицательных множителей и посчитал, что их нечетное количество.",
            "explanation": "Ученик ошибся в подсчете количества отрицательных множителей и посчитал, что их нечетное количество.",
            "plausibility": 0.75
        },
        {
            "value": "ноль",
            "value_latex": "\\text{ноль}",
            "error_type": "ai_generated",
            "error_logic": "Ученик ошибочно решил, что среди 12 чисел обязательно содержится ноль.",
            "explanation": "Ученик ошибочно решил, что среди 12 чисел обязательно содержится ноль.",
            "plausibility": 0.75
        }
    ],
    'G5_TB_6_226.4': [
        {
            "value": "707,837 < 707,829",
            "value_latex": "$707{,}837 < 707{,}829$",
            "error_type": "ai_generated",
            "error_logic": "Ученик перепутал знаки больше и меньше при сравнении разрядов единиц.",
            "explanation": "Ученик перепутал знаки больше и меньше при сравнении разрядов единиц.",
            "plausibility": 0.75
        },
        {
            "value": "707,837 = 707,829",
            "value_latex": "$707{,}837 = 707{,}829$",
            "error_type": "ai_generated",
            "error_logic": "Ученик не обратил внимания на различие в последней цифре и счел числа равными.",
            "explanation": "Ученик не обратил внимания на различие в последней цифре и счел числа равными.",
            "plausibility": 0.75
        }
    ],
    'G11_TB_11_3*_11_15_в': [
        {
            "value": "[0; 1)",
            "value_latex": "$[0; 1)$",
            "error_type": "ai_generated",
            "error_logic": "Ученик потерял вторую часть интервала решений при x > 1.",
            "explanation": "Ученик потерял вторую часть интервала решений при x > 1.",
            "plausibility": 0.75
        },
        {
            "value": "[0; 4]",
            "value_latex": "$[0; 4]$",
            "error_type": "ai_generated",
            "error_logic": "Ученик допустил ошибку при возведении обеих частей в шестую степень.",
            "explanation": "Ученик допустил ошибку при возведении обеих частей в шестую степень.",
            "plausibility": 0.75
        },
        {
            "value": "[0; +∞)",
            "value_latex": "$[0; +\\infty)$",
            "error_type": "ai_generated",
            "error_logic": "Ученик не учел точку x = 1, в которой левая и правая части обращаются в равенство.",
            "explanation": "Ученик не учел точку x = 1, в которой левая и правая части обращаются в равенство.",
            "plausibility": 0.75
        }
    ],
    'G7_ALG_1_8.4': [
        {
            "value": "(0.12 + 1.88)^2 = 4/5 * 5",
            "value_latex": "$(0.12 + 1.88)^{2} = \\dfrac{4}{5} \\cdot 5$",
            "error_type": "ai_generated",
            "error_logic": "Ученик перепутал удвоенную сумму с квадратом суммы чисел.",
            "explanation": "Ученик перепутал удвоенную сумму с квадратом суммы чисел.",
            "plausibility": 0.75
        },
        {
            "value": "2 * (0.12 + 1.88) = 4/5 + 5",
            "value_latex": "$2 \\cdot (0.12 + 1.88) = \\dfrac{4}{5} + 5$",
            "error_type": "ai_generated",
            "error_logic": "Ученик заменил умножение на сложение в правой части равенства.",
            "explanation": "Ученик заменил умножение на сложение в правой части равенства.",
            "plausibility": 0.75
        },
        {
            "value": "2 + (0.12 + 1.88) = 4/5 * 5",
            "value_latex": "$2 + (0.12 + 1.88) = \\dfrac{4}{5} \\cdot 5$",
            "error_type": "ai_generated",
            "error_logic": "Ученик прибавил двойку к сумме вместо умножения на 2.",
            "explanation": "Ученик прибавил двойку к сумме вместо умножения на 2.",
            "plausibility": 0.75
        }
    ],
    'G5_TB_6_197.1': [
        {
            "value": "73905 + 54276 = 128181",
            "value_latex": "$73905 + 54276 = 128181$",
            "error_type": "ai_generated",
            "error_logic": "Ученик ошибся в разряде десятков тысяч при подборе пропущенной цифры.",
            "explanation": "Ученик ошибся в разряде десятков тысяч при подборе пропущенной цифры.",
            "plausibility": 0.75
        },
        {
            "value": "72905 + 53276 = 126181",
            "value_latex": "$72905 + 53276 = 126181$",
            "error_type": "ai_generated",
            "error_logic": "Ученик ошибся в разряде тысяч второго слагаемого.",
            "explanation": "Ученик ошибся в разряде тысяч второго слагаемого.",
            "plausibility": 0.75
        },
        {
            "value": "72805 + 54276 = 127081",
            "value_latex": "$72805 + 54276 = 127081$",
            "error_type": "ai_generated",
            "error_logic": "Ученик ошибся в разряде сотен первого слагаемого.",
            "explanation": "Ученик ошибся в разряде сотен первого слагаемого.",
            "plausibility": 0.75
        }
    ],
    'G5_TB_11_438.1': [
        {
            "value": "60 -> 69 -> 13 -> -2 -> -24 -> -12 -> 0",
            "value_latex": "$60 \\to 69 \\to 13 \\to -2 \\to -24 \\to -12 \\to 0$",
            "error_type": "ai_generated",
            "error_logic": "Ученик ошибся на шаге деления на 3 и получил отрицательные числа.",
            "explanation": "Ученик ошибся на шаге деления на 3 и получил отрицательные числа.",
            "plausibility": 0.75
        },
        {
            "value": "60 -> 69 -> 23 -> 18 -> 96 -> 48 -> 60",
            "value_latex": "$60 \\to 69 \\to 23 \\to 18 \\to 96 \\to 48 \\to 60$",
            "error_type": "ai_generated",
            "error_logic": "Ученик вычел 5 вместо вычитания 15 на четвертом звене цепочки.",
            "explanation": "Ученик вычел 5 вместо вычитания 15 на четвертом звене цепочки.",
            "plausibility": 0.75
        },
        {
            "value": "60 -> 79 -> 23 -> 8 -> 96 -> 48 -> 60",
            "value_latex": "$60 \\to 79 \\to 23 \\to 8 \\to 96 \\to 48 \\to 60$",
            "error_type": "ai_generated",
            "error_logic": "Ученик прибавил 19 вместо прибавления 9 на первом звене цепочки.",
            "explanation": "Ученик прибавил 19 вместо прибавления 9 на первом звене цепочки.",
            "plausibility": 0.75
        }
    ]
}

for tid, dm in clean_fixes.items():
    cur.execute("SELECT correct_answer_latex, correct_answer FROM tasks_master WHERE id = %s;", (tid,))
    row = cur.fetchone()
    cal = row[0] or f"${row[1]}$"
    aol = [cal] + [d['value_latex'] for d in dm]
    cur.execute("""
        UPDATE tasks_master
        SET distractor_meta = %s,
            answer_options_latex = %s,
            latex_status = 'verified',
            updated_at = NOW()
        WHERE id = %s;
    """, (json.dumps(dm, ensure_ascii=False), json.dumps(aol, ensure_ascii=False), tid))
    print(f"✨ Исправлена задача {tid} (дистракторов: {len(dm)})")

conn.commit()
print("\nВсе 6 задач с коллизиями идеально исправлены!")
