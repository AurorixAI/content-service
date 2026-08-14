import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

fixes = {
    'G10_TB_3_4_7_3': 'Найдите область определения функции: $y = \\log_{3}(x^{2} - 2x - 3)$',
    'G10_TB_3_4_7_4': 'Найдите область определения функции: $y = \\log_{4}(x^{2} - 4)$',
    'G10_TB_3_4_7_6': 'Найдите область определения функции: $y = -\\log_{2}(x^{2} + 5x - 6)$',
    'G10_TB_3_4_9_1': 'Найдите область определения функции: $y = \\log_{x^{2}}(4 - x)$',
    'G10_TB_3_4_9_4': 'Найдите область определения функции: $f(x) = \\sqrt{x+4} + \\log_{2}(x^{2} - 4)$',
    'G10_TB_3_4_9_5': 'Найдите область определения функции: $f(x) = \\dfrac{\\log_{x^{2}+1}(6-x)}{\\sqrt{x+2}}$'
}

for tid, ql in fixes.items():
    cur.execute("""
        UPDATE tasks_master
        SET question_latex = %s,
            latex_status = 'verified',
            updated_at = NOW()
        WHERE id = %s;
    """, (ql, tid))
    print(f"✨ Restored pristine {tid}: {ql}")

conn.commit()
print("All 6 logarithmic tasks restored to pristine KaTeX!")
