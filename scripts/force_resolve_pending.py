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

SCHOOL_VERIFY_SYSTEM_PROMPT = """Ты — эксперт-методист по математике для средней школы.
Твоя задача — проверить правильность математического ответа на задачу из школьного учебника 9 класса.
Входные данные:
1. Вопрос/Условие задачи.
2. Предполагаемый ответ (из учебника).
3. Тип ответа (expression, inequality, equation_solution, text, set и т.д.).

ПРАВИЛА И КОНТЕКСТ ШКОЛЫ:
1. Мы работаем строго в рамках школьной программы 9 класса. КОМПЛЕКСНЫЕ ЧИСЛА НЕ СУЩЕСТВУЮТ. Если дискриминант квадратного уравнения отрицательный — корней нет. Действительные корни являются полным и окончательным ответом.
2. Стандартный символ корня '√' является валидным математическим обозначением.
3. Если ответ из учебника содержит опечатку (например, перепутаны границы интервала '(-7; -8)' вместо '(-8; -7)', или лишний посторонний корень в системе, или неверный знак), ты должен:
   - Вычислить математически правильный школьный ответ.
   - Указать is_corrected = true.
   - Вернуть исправленный ответ в поле correct_answer (как обычный текст) и в поле correct_answer_latex.
4. Если ответ полностью верный (или ты его исправил), укажи is_correct = true.
5. Если в условии задачи критическая ошибка/опечатка (отсутствует функция, нет данных), из-за которой её в принципе невозможно решить, укажи is_valid = false.
6. LaTeX-ответ возвращай без знаков $ снаружи, просто чистый LaTeX-код.

Верни результат строго в формате JSON:
{
  "is_valid": true / false,
  "is_correct": true / false,
  "is_corrected": true / false,
  "correct_answer": "исправленный_или_оригинальный_текстовый_ответ",
  "correct_answer_latex": "красивый_latex_код",
  "explanation": "краткое объяснение твоего решения"
}"""

DISTRACTOR_SYSTEM_PROMPT = """Ты — опытный учитель математики. Твоя задача — сгенерировать ровно 3 неверных ответа (дистрактора) к школьной задаче на основе типичных ошибок учеников.

Правила:
1. Дистракторы должны отличаться друг от друга и быть математически неверными.
2. Ни один дистрактор не равен правильному ответу.
3. Для каждого дистрактора укажи:
   - value: текстовое значение дистрактора.
   - value_latex: LaTeX-код дистрактора (без знаков $).
   - error_logic: описание конкретного неверного шага решения (минимум 25 символов на русском языке).
   - explanation: то же самое.
   - plausibility: 0.75.
4. Верни JSON:
{
  "distractors": [
    {
      "value": "неверный_ответ",
      "value_latex": "latex",
      "error_logic": "...",
      "explanation": "...",
      "plausibility": 0.75
    },
    ...
  ]
}"""

def verify_and_correct_task(task: dict) -> dict:
    prompt = f"Задача: {task['question_text']}\nОтвет из учебника: {task['correct_answer']}\nТип ответа: {task['answer_type']}"
    try:
        res_text = call_deepseek(prompt, system_prompt=SCHOOL_VERIFY_SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.1)
        parsed = parse_json_response(res_text)
        if isinstance(parsed, dict) and "is_correct" in parsed:
            return parsed
    except Exception as e:
        log.error(f"Failed to verify task {task['id']} via DeepSeek: {e}")
    return {"is_valid": True, "is_correct": False, "is_corrected": False, "correct_answer": task['correct_answer'], "correct_answer_latex": "", "explanation": "DeepSeek API error"}

def generate_distractors(task: dict, correct_answer: str) -> list:
    a_lower = correct_answer.strip().lower()
    is_binary = a_lower in {"да", "нет", "верно", "неверно", "true", "false"}
    
    if is_binary:
        opp = "нет" if "да" in a_lower or "верно" in a_lower or "true" in a_lower else "да"
        error_logic = f"Ученик выбрал неверную альтернативу '{opp}' вместо '{correct_answer}'."
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
    parser.add_argument("--limit", type=int, default=150, help="Limit number of tasks to process")
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
    log.info(f"Loaded {len(tasks)} pending tasks for school adaptation.")

    verified_count = 0
    corrected_count = 0
    invalid_count = 0

    for task in tasks:
        log.info(f"Processing task {task['id']} | Answer: {task['correct_answer']}")
        
        res = verify_and_correct_task(task)
        
        if not res.get("is_valid"):
            log.warning(f"  -> Task condition is INVALID: {res.get('explanation')}")
            invalid_count += 1
            if not args.dry_run:
                tags = dict(task['tags'] or {})
                tags["invalid_task"] = True
                tags["invalid_reason"] = res.get("explanation", "condition_broken")
                cur.execute('''
                    UPDATE tasks_master
                    SET tags = %s
                    WHERE id = %s
                ''', (json.dumps(tags), task['id']))
                conn.commit()
            continue

        if res.get("is_correct") or res.get("is_corrected"):
            latex_ans = res['correct_answer_latex'].strip()
            if not latex_ans.startswith("$") and latex_ans:
                latex_ans = f"${latex_ans}$"
            
            final_ans_text = res.get("correct_answer", task['correct_answer'])
            is_corrected = res.get("is_corrected", False)
            
            if is_corrected:
                log.info(f"  -> Corrected! New Answer: {final_ans_text} | LaTeX: {latex_ans}")
                corrected_count += 1
            else:
                log.info(f"  -> Verified school answer! LaTeX: {latex_ans}")
            
            # Генерация дистракторов
            dist_meta = generate_distractors(task, final_ans_text)
            
            if not args.dry_run:
                tags = dict(task['tags'] or {})
                tags["reverified_by"] = "deepseek_school"
                tags["verification_explanation"] = res.get("explanation", "")
                if is_corrected:
                    tags["corrected_school_answer"] = True
                    tags["original_answer_before_correction"] = task['correct_answer']
                
                cur.execute('''
                    UPDATE tasks_master
                    SET verification_status = 'verified',
                        correct_answer = %s,
                        correct_answer_latex = %s,
                        distractor_meta = %s,
                        tags = %s
                    WHERE id = %s
                ''', (final_ans_text, latex_ans, json.dumps(dist_meta), json.dumps(tags), task['id']))
                conn.commit()
            
            verified_count += 1
        else:
            log.warning(f"  -> Verification failed: {res.get('explanation')}")
            if not args.dry_run:
                tags = dict(task['tags'] or {})
                tags["verification_failed_reason"] = res.get("explanation", "rejected_by_school_gate")
                cur.execute('''
                    UPDATE tasks_master
                    SET tags = %s
                    WHERE id = %s
                ''', (json.dumps(tags), task['id']))
                conn.commit()

    log.info(f"Done. Verified/Corrected: {verified_count}/{len(tasks)} (Corrected: {corrected_count}). Invalid tasks: {invalid_count}.")
    conn.close()

if __name__ == "__main__":
    main()
