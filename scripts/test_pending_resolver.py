import os
import sys
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("resolve_all_pending")

SYSTEM_PROMPT = """Ты — ведущий математик-эксперт и ИИ-верификатор образовательной платформы.
Твоя задача — строго и профессионально проверить математическую корректность задачи, эталонного ответа и сгенерировать 3 качественных дистрактора (неверных варианта ответа с описанием логики ошибки).

Входные данные:
1. Вопрос/Условие задачи.
2. Исходный ответ из учебника/базы.

Инструкции:
1. Тщательно реши задачу самостоятельно.
2. Сравни своё решение с исходным ответом:
   - Если исходный ответ правильный, установи is_correct: true.
   - Если исходный ответ имеет верный смысл, но не идеальную формулу (например, словесное описание или отсутствие скобок), приведи его к каноническому виду и установи is_correct: true.
   - Если в условии или ответе фатальная ошибка/противоречие, установи is_correct: false.
3. Сформулируй:
   - correct_answer_latex: идеальный ответ в LaTeX (без внешних $).
   - real_answer_type: один из типов ['expression', 'inequality', 'equation_solution', 'interval', 'text', 'multiple_choice', 'exact_number'].
   - explanation: математическое доказательство решения (2-4 предложения).
4. Сгенерируй ровно 3 дистрактора на типичные ошибки школьников:
   - value: текстовое значение дистрактора.
   - value_latex: LaTeX значение (без внешних $).
   - error_logic: подробное описание ошибки мышления ученика (почему и где он ошибся, от 25 символов на русском).
   - explanation: дубликат error_logic.
   - plausibility: 0.75.

Верни СТРОГО JSON:
{
  "is_correct": true / false,
  "real_answer_type": "...",
  "correct_answer_latex": "...",
  "explanation": "...",
  "distractors": [
    {
      "value": "...",
      "value_latex": "...",
      "error_logic": "...",
      "explanation": "...",
      "plausibility": 0.75
    },
    ...
  ]
}"""

def process_pending_task(task):
    prompt = f"УСЛОВИЕ ЗАДАЧИ:\n{task['question_text']}\n\nИСХОДНЫЙ ОТВЕТ:\n{task['correct_answer']}"
    try:
        res_text = call_deepseek(prompt, system_prompt=SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.1)
        parsed = parse_json_response(res_text)
        if isinstance(parsed, dict) and "is_correct" in parsed:
            return parsed
    except Exception as e:
        log.error(f"Error processing {task['id']}: {e}")
    return None

def main():
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, question_text, correct_answer, answer_type, tags, distractor_meta
        FROM tasks_master
        WHERE verification_status = 'pending'
        ORDER BY id
        LIMIT 5;
    """)
    tasks = cur.fetchall()
    log.info(f"Loaded {len(tasks)} sample pending tasks for test verification.")

    for t in tasks:
        log.info(f"\n--- Testing {t['id']} ---")
        log.info(f"Q: {t['question_text'][:100]}...")
        log.info(f"A: {t['correct_answer']}")
        
        res = process_pending_task(t)
        log.info(f"DeepSeek result: is_correct={res.get('is_correct') if res else None}")
        if res:
            log.info(f"Type: {res.get('real_answer_type')}")
            log.info(f"LaTeX: {res.get('correct_answer_latex')}")
            log.info(f"Distractors count: {len(res.get('distractors', []))}")
            for idx, d in enumerate(res.get('distractors', [])):
                log.info(f"  D[{idx}]: {d.get('value_latex')} | {d.get('error_logic')[:60]}...")

    conn.close()

if __name__ == '__main__':
    main()
