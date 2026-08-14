import psycopg2, json, sys

sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')
from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response

conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
cur = conn.cursor()

tid = 'G10_TB_§17_17_2_1'

PROMPT = """Задача: Найди значение выражения sin(420 градусов).
Правильный ответ: sqrt(3)/2, так как sin(420) = sin(360+60) = sin(60) = sqrt(3)/2

Создай 3 правдоподобных неверных дистрактора с педагогическим описанием ошибки.

Верни JSON массив из 3 объектов:
[
  {
    "value": "latex_выражение",
    "value_latex": "latex_выражение_для_рендера",
    "error_logic": "Описание ошибки ученика 30-80 слов",
    "error_logic_latex": "Описание ошибки с LaTeX формулами в долларах",
    "plausibility": 0.75
  }
]

Варианты ошибок:
1) Ученик путает sin60 с cos60 и пишет 1/2
2) Ученик думает что 420 в IV четверти и берет -sqrt(3)/2
3) Ученик не приводит угол и вычисляет sin(60) = sqrt(3)/2 верно, но ошибается в знаке при 420 и пишет 0
"""

res = call_deepseek(PROMPT, model=get_deepseek_model(), temperature=0.1)
parsed = parse_json_response(res)
print('Generated:', json.dumps(parsed, ensure_ascii=False, indent=2))

if parsed and isinstance(parsed, list) and len(parsed) >= 3:
    distractors = parsed[:3]
    for d in distractors:
        d['error_type'] = 'ai_generated'
        d['explanation'] = d.get('error_logic', '')
        d['explanation_latex'] = d.get('error_logic_latex', '')
    
    cur.execute(
        'UPDATE tasks_master SET distractor_meta = %s, updated_at = NOW() WHERE id = %s;',
        (json.dumps(distractors, ensure_ascii=False), tid)
    )
    conn.commit()
    print(f'\n✅ Задача {tid}: дистракторы полностью регенерированы!')
else:
    print('❌ Ошибка парсинга ответа LLM')
