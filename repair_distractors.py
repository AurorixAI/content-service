"""
One-off repair: generate distractors + fix solution_steps for problem tasks.
Run inside content-worker: docker exec -it content-worker python /tmp/repair_distractors.py
"""
import json, sys, os
sys.path.insert(0, "/app")

from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response
from src.core.database import _get_engine
from sqlalchemy import text

engine = _get_engine()

def ai_distractors(question_text: str, correct_answer: str) -> list:
    prompt = (
        "Ты — опытный учитель математики 5 класса.\n"
        "Придумай ровно 3 правдоподобных НЕВЕРНЫХ ответа, которые ученик мог бы дать из-за типичных ошибок.\n\n"
        f"Вопрос: {question_text}\n"
        f"Правильный ответ: {correct_answer}\n\n"
        "Требования:\n"
        "- Каждый дистрактор — конкретный неверный ответ (не объяснение)\n"
        "- Объясни конкретную ошибку ученика (перепутал действие, ошибся в разряде и т.д.)\n"
        "- Ответы должны быть близки по формату к правильному\n\n"
        'Верни ТОЛЬКО JSON: [{"value":"...","explanation":"..."}]'
    )
    try:
        text_resp = call_gemini(prompt, model=get_pro_model(), temperature=0.3, max_tokens=1024)
        items = parse_json_response(text_resp)
        if isinstance(items, list) and items:
            return [
                {
                    "value": d.get("value", ""),
                    "error_type": "ai_generated",
                    "explanation": d.get("explanation", ""),
                    "plausibility": 0.75,
                }
                for d in items[:3]
            ]
    except Exception as e:
        print(f"  Gemini failed: {e}")
    return []


def ai_enrich(question_text: str, correct_answer: str) -> dict:
    prompt = (
        "Ты — эксперт-методист по математике 5 класса. Для задачи ниже сгенерируй:\n"
        "1. solution_steps: пошаговое решение (3-5 шагов)\n"
        "2. hints: 2-3 подсказки для ученика\n"
        "3. common_mistakes: 2-3 типичные ошибки\n\n"
        f"Вопрос: {question_text}\n"
        f"Правильный ответ: {correct_answer}\n\n"
        'Верни ТОЛЬКО JSON:\n'
        '{"solution_steps":["Шаг 1: ..."],"hints":["..."],"common_mistakes":[{"mistake":"...","explanation":"...","wrong_answer":"..."}]}'
    )
    try:
        text_resp = call_gemini(prompt, model=get_pro_model(), temperature=0.2, max_tokens=2048)
        data = parse_json_response(text_resp)
        if isinstance(data, dict):
            return data
    except Exception as e:
        print(f"  Enrich failed: {e}")
    return {}


with engine.connect() as conn:
    # 1. Find tasks missing distractors
    rows = conn.execute(text("""
        SELECT id, answer_type, correct_answer, question_text
        FROM tasks_master
        WHERE distractor_meta IS NULL
           OR distractor_meta = 'null'
           OR distractor_meta = '[]'
        ORDER BY id
    """)).fetchall()

    print(f"Found {len(rows)} tasks missing distractors")
    for row in rows:
        task_id, atype, correct_answer, question_text = row
        print(f"  Generating distractors for {task_id} ({atype})...")
        distractors = ai_distractors(question_text or "", correct_answer or "")
        if distractors:
            conn.execute(text("""
                UPDATE tasks_master
                SET distractor_meta = :dm, updated_at = NOW()
                WHERE id = :id
            """), {"dm": json.dumps(distractors, ensure_ascii=False), "id": task_id})
            print(f"    ✓ {len(distractors)} distractors written")
        else:
            print(f"    ✗ failed")

    # 2. Find tasks missing solution_steps
    rows2 = conn.execute(text("""
        SELECT id, answer_type, correct_answer, question_text
        FROM tasks_master
        WHERE solution_steps IS NULL OR solution_steps = '[]'
        ORDER BY id
    """)).fetchall()

    print(f"\nFound {len(rows2)} tasks missing solution_steps")
    for row in rows2:
        task_id, atype, correct_answer, question_text = row
        print(f"  Enriching {task_id}...")
        enriched = ai_enrich(question_text or "", correct_answer or "")
        if enriched:
            steps = enriched.get("solution_steps", [])
            hints = enriched.get("hints", [])
            mistakes = enriched.get("common_mistakes", [])
            if steps:
                conn.execute(text("""
                    UPDATE tasks_master
                    SET solution_steps = :steps,
                        hints = CASE WHEN hints IS NULL OR hints = '[]' THEN :hints ELSE hints END,
                        common_mistakes = CASE WHEN common_mistakes IS NULL OR common_mistakes = '[]' THEN :mistakes ELSE common_mistakes END,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "steps": json.dumps(steps, ensure_ascii=False),
                    "hints": json.dumps(hints, ensure_ascii=False),
                    "mistakes": json.dumps(mistakes, ensure_ascii=False),
                    "id": task_id,
                })
                print(f"    ✓ {len(steps)} steps written")
            else:
                print(f"    ✗ no steps returned")
        else:
            print(f"    ✗ failed")

    conn.commit()

# Final check
with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT
          COUNT(*) AS total,
          COUNT(CASE WHEN distractor_meta IS NULL OR distractor_meta = 'null' OR distractor_meta = '[]' THEN 1 END) AS no_distractors,
          COUNT(CASE WHEN solution_steps IS NULL OR solution_steps = '[]' THEN 1 END) AS no_steps
        FROM tasks_master
    """)).fetchone()
    print(f"\n=== FINAL ===")
    print(f"Total: {r[0]}, Missing distractors: {r[1]}, Missing steps: {r[2]}")
