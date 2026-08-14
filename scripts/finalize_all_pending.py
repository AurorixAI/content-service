import psycopg2
import json

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

rejections = {
    'DIFF_G7_S32_03_C_02': 'Уравнение площади (5-3k)^2 = 18(-k) сводится к 9k^2-12k+25=0 с отрицательным дискриминантом D=-756<0. Действительных решений нет.',
    'DIFF_G7_S21_01_C_02': 'Арифметическая ошибка в учебнике: (79^3 - 39^3)/160 = 433720/160 = 2710.75, ответ 3043 неверен.',
    'DIFF_G6_S31_02_C_01': 'Уравнение движения -15 + 8*4 - 3n = -5 дает n = 22/3, что не является целым числом прыжков.',
    'GEN_G7_S14_02_C_01': 'Противоречие в условии: умножение частного на делитель дает исходное число минус 15, что не может равняться исходному числу минус 24 (-15 != -24).',
    'DIFF_G7_S09_02_C_01': 'Поврежденная разметка формулы в первоисточнике: двоеточие внутри алгебраического выражения.',
    'DIFF_G7_S32_05_C_02': 'Уравнение площади (3k+5)^2 = 20k дает 9k^2+10k+25=0 с отрицательным дискриминантом D=-800<0. Действительных решений k нет.',
    'ds_llm_fcbb4b6c3d66': 'Уравнение касательной (2x-3)/(x^2-3x+4) = 2 дает 2x^2-8x+11=0 с отрицательным дискриминантом D=-24<0. Действительных точек x_0 нет.'
}

print("=== 🏁 ФИНАЛЬНАЯ ЗАКРЫТИЕ ПОСЛЕДНИХ 7 PENDING ЗАДАЧ ===")

for tid, reason in rejections.items():
    cur.execute("SELECT tags FROM tasks_master WHERE id = %s;", (tid,))
    row = cur.fetchone()
    tags = dict(row[0] if row and row[0] else {})
    tags["smart_verify_status"] = "rejected"
    tags["rejection_reason"] = reason
    
    cur.execute("""
        UPDATE tasks_master
        SET verification_status = 'rejected',
            tags = %s,
            updated_at = NOW()
        WHERE id = %s;
    """, (json.dumps(tags, ensure_ascii=False), tid))
    print(f"🚫 REJECTED {tid}: {reason}")

conn.commit()

# Проверяем остаток pending
cur.execute("SELECT count(*) FROM tasks_master WHERE verification_status = 'pending';")
cnt = cur.fetchone()[0]
print(f"\n🎉 ОСТАТОК PENDING В БАЗЕ: {cnt} ЗАДАЧ!")
