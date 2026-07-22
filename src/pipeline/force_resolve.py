"""
force_resolve.py — финальный шаг пайплайна.

После основного SmartVerify и post_processing автоматически находит все
оставшиеся pending задачи учебника и закрывает их через DeepSeek:
- математически верифицирует ответ
- генерирует корректный LaTeX
- исправляет опечатки учебника
- помечает невалидные задачи (нет условия/графика)

Вызывается из src/worker/tasks.py как нефатальный шаг.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import re

import psycopg2
from psycopg2.extras import RealDictCursor

# Добавляем корень проекта в path (на случай запуска напрямую)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

log = logging.getLogger(__name__)

SCHOOL_VERIFY_SYSTEM_PROMPT = """Ты — эксперт-математик и методист. Твоя задача — верифицировать и отформатировать в LaTeX ответ к задаче из учебника по алгебре для 10 класса.

Входные данные:
1. Вопрос/Условие задачи.
2. Ответ из учебника.
3. Тип ответа (expression, inequality, text, set и т.д.).

ПРАВИЛА ВЕРИФИКАЦИИ:
1. Ответ из учебника верен в 98% случаев. Проведи точный математический расчет в уме.
2. Проверь область определения (ОДЗ). Напоминание: для исследования четности/нечетности область определения должна быть строго симметрична относительно нуля. Если точка (например, x = -6) исключена из ОДЗ, а симметричная ей (x = 6) нет, то функция НЕ является ни четной, ни нечетной.
3. Перед сравнением иррациональных чисел (например, 7√(1/7) и 0.5√20) переведи их в десятичный вид: 7√(1/7) = √7 ≈ 2.64, 0.5√20 = √5 ≈ 2.23. Так как 2.64 > 2.23, то знак '>'. Не меняй верные знаки сравнения!
4. Если ответ из учебника математически верен и эквивалентен условию, верни:
   "is_correct": true, "is_corrected": false, "correct_answer": [исходный ответ]
5. Если в ответе учебника явная опечатка (например, перепутан знак или арифметическая ошибка), вычисли правильный ответ и верни:
   "is_correct": true, "is_corrected": true, "correct_answer": [исправленный ответ]
6. Если условие задачи некорректно (например, пропущена часть текста или графика, из-за чего решить невозможно), верни:
   "is_valid": false
7. В поле "correct_answer_latex" верни чистый LaTeX-код ответа БЕЗ знаков $ снаружи.

Формат вывода — строго JSON:
{
  "explanation": "пошаговое объяснение расчетов",
  "is_valid": true/false,
  "is_correct": true/false,
  "is_corrected": true/false,
  "correct_answer": "текст",
  "correct_answer_latex": "latex"
}"""


def _call_deepseek(db_url: str, question: str, answer: str, answer_type: str, class_level: int) -> dict | None:
    """Вызов DeepSeek через pipeline-клиент."""
    try:
        from src.pipeline.deepseek_client import call_deepseek, parse_json_response

        user_msg = (
            f"Класс: {class_level}\n"
            f"Тип ответа: {answer_type}\n"
            f"Условие задачи: {question}\n"
            f"Ответ из учебника: {answer}"
        )
        raw = call_deepseek(
            prompt=user_msg,
            system_prompt=SCHOOL_VERIFY_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=2048,
        )
        return parse_json_response(raw)
    except Exception as exc:
        log.warning("DeepSeek call failed: %s", exc)
        return None



def force_resolve_pending(
    db_url: str,
    textbook_id: str,
    class_level: int,
) -> dict:
    """
    Находит все pending задачи данного учебника и закрывает их через DeepSeek.

    Returns:
        {"verified": int, "corrected": int, "failed": int, "invalid": int}
    """
    stats = {"verified": 0, "corrected": 0, "failed": 0, "invalid": 0}

    try:
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
    except Exception as exc:
        log.error("force_resolve: cannot connect to DB: %s", exc)
        return stats

    try:
        with conn:
            cur = conn.cursor()

            # Находим все pending задачи учебника
            cur.execute(
                """
                SELECT tm.id, tm.question_text, tm.correct_answer,
                       tm.answer_type, tm.correct_answer_latex
                FROM tasks_master tm
                JOIN textbook_tasks tt ON tt.task_id = tm.id
                WHERE tt.textbook_id = CAST(%(textbook_id)s AS UUID)
                  AND tm.verification_status = 'pending'
                ORDER BY tm.id
                """,
                {"textbook_id": textbook_id},
            )
            pending_tasks = cur.fetchall()

        if not pending_tasks:
            log.info("force_resolve: no pending tasks for textbook %s", textbook_id)
            return stats

        log.info("force_resolve: found %d pending tasks for textbook %s", len(pending_tasks), textbook_id)

        for task in pending_tasks:
            task_id = task["id"]
            question = task["question_text"] or ""
            answer = task["correct_answer"] or ""
            answer_type = task["answer_type"] or "expression"

            log.info("force_resolve: processing %s | answer: %s", task_id, answer[:60])

            result = _call_deepseek(db_url, question, answer, answer_type, class_level)

            if result is None:
                # API недоступен — оставляем pending, не ломаем пайплайн
                stats["failed"] += 1
                log.warning("force_resolve: API error for task %s — keeping pending", task_id)
                continue

            is_valid = result.get("is_valid", True)
            is_correct = result.get("is_correct", False)
            is_corrected = result.get("is_corrected", False)
            latex = result.get("correct_answer_latex", "") or ""
            new_answer = result.get("correct_answer", answer) or answer

            # Убираем лишние $ если модель их добавила
            latex = re.sub(r"^\$+|\$+$", "", latex.strip())

            if not is_valid:
                # Фатально невалидная задача — помечаем и деактивируем
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE tasks_master
                        SET verification_status = 'invalid_task',
                            is_active = false,
                            tags = tags || '{"invalid_task": true}'::jsonb,
                            updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {"id": task_id},
                    )
                stats["invalid"] += 1
                log.info("force_resolve: %s marked invalid_task", task_id)

            elif is_correct or is_corrected:
                # Успешно верифицирована или исправлена
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE tasks_master
                        SET verification_status = 'verified',
                            correct_answer_latex = %(latex)s,
                            correct_answer = %(answer)s,
                            updated_at = now()
                        WHERE id = %(id)s
                        """,
                        {
                            "id": task_id,
                            "latex": latex if latex else task["correct_answer_latex"],
                            "answer": new_answer,
                        },
                    )
                if is_corrected:
                    stats["corrected"] += 1
                    log.info("force_resolve: %s corrected → %s", task_id, new_answer[:60])
                else:
                    stats["verified"] += 1
                    log.info("force_resolve: %s verified ✓", task_id)
            else:
                # Модель не смогла верифицировать — оставляем pending
                stats["failed"] += 1
                log.warning("force_resolve: %s could not be verified — keeping pending", task_id)

    except Exception as exc:
        log.error("force_resolve: unexpected error: %s", exc)
    finally:
        conn.close()

    log.info(
        "force_resolve done: verified=%d corrected=%d invalid=%d failed=%d",
        stats["verified"], stats["corrected"], stats["invalid"], stats["failed"],
    )
    return stats


if __name__ == "__main__":
    # Можно запустить напрямую для ручного прогона:
    # python -m src.pipeline.force_resolve <textbook_id> <class_level>
    import argparse
    from src.core.config import get_settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Force-resolve pending tasks via DeepSeek")
    parser.add_argument("textbook_id", help="UUID учебника")
    parser.add_argument("class_level", type=int, help="Класс (5-11)")
    args = parser.parse_args()

    settings = get_settings()
    result = force_resolve_pending(
        db_url=settings.database_url,
        textbook_id=args.textbook_id,
        class_level=args.class_level,
    )
    print(f"\nРезультат: {result}")
