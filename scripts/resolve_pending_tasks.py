#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

# Добавляем корень проекта в пути поиска модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import get_settings
from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)

TEXTBOOK_ID = '2aa7af81-af13-42f9-a26b-e7e6bebaa4e6'

VERIFY_SYSTEM_PROMPT = """Ты — эксперт-математик и ИИ-верификатор учебного контента.
Твоя задача — проверить правильность математического ответа на вопрос/задачу из школьного учебника.
Входные данные:
1. Вопрос/Условие задачи.
2. Предполагаемый ответ (в текстовом виде).
3. Тип ответа (например, expression, inequality, equation_solution, text, set и т.д.).

Правила:
1. Проверь, является ли предполагаемый ответ математически точным и правильным для этого вопроса.
2. Переведи ответ в красивый, канонический LaTeX-формат. Не оборачивай его в знаки $, просто верни чистый LaTeX-код.
3. В LaTeX-ответе ИЗБЕГАЙ слов вроде 'False' или 'True' (например, если корни системы x=4, y=2, то LaTeX должен быть x_1=4, y_1=2 или аналогичный, но НЕ False).
4. Если ответ полностью верен, укажи is_correct = true. Если ответ ошибочен или содержит критический математический бред, укажи is_correct = false.
5. Верни результат строго в формате JSON:
{
  "is_correct": true / false,
  "correct_answer_latex": "красивый_latex_код",
  "explanation": "краткое объяснение верификации"
}"""

DISTRACTOR_SYSTEM_PROMPT = """Ты — опытный учитель математики. Твоя задача — сгенерировать ровно 3 правдоподобных неверных ответа (дистрактора) к задаче на основе типичных ошибок, которые совершают школьники при решении.

Правила генерации дистракторов:
1. Каждый дистрактор должен быть правдоподобным (получаться при неверном знаке, забытом коэффициенте, ошибке в арифметике и т.д.).
2. Ни один дистрактор не должен быть равен или математически эквивалентен правильному ответу.
3. Все дистракторы должны отличаться друг от друга.
4. Для каждого дистрактора укажи:
   - value: текстовое значение дистрактора.
   - value_latex: LaTeX-код дистрактора (без знаков $ снаружи).
   - error_logic: описание конкретного неверного шага решения (минимум 25 символов на русском языке, без общих фраз вроде "ошибка в расчете").
   - explanation: то же самое, что и error_logic.
   - plausibility: 0.75.
5. Верни результат строго в формате JSON:
{
  "distractors": [
    {
      "value": "неверный_ответ_1",
      "value_latex": "latex_1",
      "error_logic": "Ученик забыл поменять знак неравенства при делении на отрицательное число...",
      "explanation": "...",
      "plausibility": 0.75
    },
    ...
  ]
}"""

def verify_task_with_deepseek(task: dict) -> dict:
    prompt = f"Задача: {task['question_text']}\nПредполагаемый ответ: {task['correct_answer']}\nТип ответа: {task['answer_type']}"
    try:
        res_text = call_deepseek(prompt, system_prompt=VERIFY_SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.1)
        parsed = parse_json_response(res_text)
        if isinstance(parsed, dict) and "is_correct" in parsed:
            return parsed
    except Exception as e:
        log.error(f"Failed to verify task {task['id']} via DeepSeek: {e}")
    return {"is_correct": False, "correct_answer_latex": "", "explanation": "DeepSeek API error"}

def generate_distractors_with_deepseek(task: dict, correct_answer: str) -> list:
    a_lower = correct_answer.strip().lower()
    is_binary = a_lower in {"да", "нет", "верно", "неверно", "true", "false"}
    
    if is_binary:
        opp = "нет" if "да" in a_lower or "верно" in a_lower or "true" in a_lower else "да"
        error_logic = f"Ученик выбрал неверную логическую альтернативу '{opp}' вместо '{correct_answer}'."
        return [{
            "value": opp,
            "value_latex": opp,
            "error_type": "ai_generated",
            "error_logic": error_logic,
            "explanation": error_logic,
            "plausibility": 0.75
        }]

    prompt = f"Задача: {task['question_text']}\nПравильный ответ: {correct_answer}\nТип ответа: {task['answer_type']}"
    try:
        res_text = call_deepseek(prompt, system_prompt=DISTRACTOR_SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.4)
        parsed = parse_json_response(res_text)
        if isinstance(parsed, dict) and "distractors" in parsed:
            items = parsed["distractors"]
            meta = []
            for item in items:
                meta.append({
                    "value": str(item.get("value", "")),
                    "error_type": "ai_generated",
                    "error_logic": str(item.get("error_logic", "")),
                    "explanation": str(item.get("explanation", item.get("error_logic", ""))),
                    "value_latex": str(item.get("value_latex", item.get("value", ""))),
                    "plausibility": 0.75
                })
            return meta
    except Exception as e:
        log.error(f"Failed to generate distractors for task {task['id']} via DeepSeek: {e}")
    return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Do not save changes to DB")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of tasks to process")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL is not set!")
        sys.exit(1)

    conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute('''
        SELECT tm.id, tm.question_text, tm.correct_answer, tm.correct_answer_latex, tm.answer_type, tm.tags, tm.distractor_meta
        FROM tasks_master tm 
        JOIN textbook_toc toc ON toc.id = tm.toc_id 
        WHERE toc.textbook_id = %s AND tm.verification_status = 'pending'
        ORDER BY tm.id
        LIMIT %s
    ''', (TEXTBOOK_ID, args.limit))
    
    tasks = cur.fetchall()
    log.info(f"Loaded {len(tasks)} pending tasks.")

    verified_count = 0
    updated_distractors = 0

    for task in tasks:
        log.info(f"Processing task {task['id']} | Answer: {task['correct_answer']}")
        
        res = verify_task_with_deepseek(task)
        
        if res.get("is_correct"):
            log.info(f"  -> Verified successfully! LaTeX: {res['correct_answer_latex']}")
            latex_ans = res['correct_answer_latex'].strip()
            if not latex_ans.startswith("$") and latex_ans:
                latex_ans = f"${latex_ans}$"
                
            dist_meta = task['distractor_meta']
            need_distractors = False
            if not dist_meta or len(dist_meta) < (1 if task['correct_answer'].strip().lower() in ["да", "нет"] else 3):
                need_distractors = True
                
            if need_distractors:
                log.info("  -> Generating distractors...")
                new_dist = generate_distractors_with_deepseek(task, task['correct_answer'])
                if new_dist:
                    dist_meta = new_dist
                    updated_distractors += 1
                    log.info(f"  -> Successfully generated {len(new_dist)} distractors.")
                else:
                    log.warning("  -> Distractor generation returned empty.")

            if not args.dry_run:
                tags = dict(task['tags'] or {})
                tags["reverified_by"] = "deepseek"
                tags["verification_explanation"] = res.get("explanation", "")
                
                cur.execute('''
                    UPDATE tasks_master
                    SET verification_status = 'verified',
                        correct_answer_latex = %s,
                        distractor_meta = %s,
                        tags = %s
                    WHERE id = %s
                ''', (latex_ans, json.dumps(dist_meta), json.dumps(tags), task['id']))
                conn.commit()
            
            verified_count += 1
        else:
            log.warning(f"  -> Verification failed: {res.get('explanation', 'Not correct')}")
            if not args.dry_run:
                tags = dict(task['tags'] or {})
                tags["verification_failed_reason"] = res.get("explanation", "deepseek_rejected")
                cur.execute('''
                    UPDATE tasks_master
                    SET tags = %s
                    WHERE id = %s
                ''', (json.dumps(tags), task['id']))
                conn.commit()

    log.info(f"Done. Verified: {verified_count}/{len(tasks)}. Generated distractors for: {updated_distractors} tasks.")
    conn.close()

if __name__ == "__main__":
    main()
