import os
import sys
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response
from scripts.backfill_latex_deepseek import (
    final_display_issues,
    latex_status_from_issues,
    validate_display_contract,
    validate_professional_latex,
    validate_with_katex,
    _json_list
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("resolve_all_pending_parallel")

SYSTEM_PROMPT = """Ты — ведущий математик-эксперт и ИИ-верификатор школьной образовательной платформы.
Твоя задача — строго и профессионально проверить математическую корректность задачи, эталонного ответа и сгенерировать 3 качественных дистрактора (неверных варианта ответа с описанием логики ошибки).

Входные данные:
1. Вопрос/Условие задачи.
2. Исходный ответ из учебника/базы.

Инструкции:
1. Тщательно реши задачу самостоятельно шаг за шагом.
2. Сравни своё аналитическое решение с исходным ответом:
   - Если исходный ответ математически верен, установи is_correct: true.
   - Если исходный ответ верен по сути, но выражен словесно или требует упрощения (например, тождество доказано, или ответ в виде промежутка/множества), приведи его к каноническому виду и установи is_correct: true.
   - Если в условии или ответе содержится неустранимая ошибка или противоречие в исходнике, установи is_correct: false.
3. Сформулируй:
   - correct_answer_latex: идеальный ответ в LaTeX (без внешних $).
   - real_answer_type: один из типов ['expression', 'inequality', 'equation_solution', 'interval', 'text', 'multiple_choice', 'exact_number'].
   - explanation: строгое математическое доказательство решения (2-3 предложения).
4. Сгенерируй ровно 3 дистрактора на типичные ошибки школьников:
   - value: текстовое значение дистрактора.
   - value_latex: LaTeX значение (без внешних $).
   - error_logic: подробное описание ошибки мышления ученика (почему и где он ошибся, от 25 символов на русском языке, без общих фраз).
   - explanation: дубликат error_logic.
   - plausibility: 0.75.

Верни СТРОГО валидный JSON:
{
  "is_correct": true,
  "real_answer_type": "expression",
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
    {
      "value": "...",
      "value_latex": "...",
      "error_logic": "...",
      "explanation": "...",
      "plausibility": 0.75
    },
    {
      "value": "...",
      "value_latex": "...",
      "error_logic": "...",
      "explanation": "...",
      "plausibility": 0.75
    }
  ]
}"""

def process_task(task):
    prompt = f"УСЛОВИЕ ЗАДАЧИ:\n{task['question_text']}\n\nИСХОДНЫЙ ОТВЕТ:\n{task['correct_answer']}"
    try:
        res_text = call_deepseek(prompt, system_prompt=SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.1)
        parsed = parse_json_response(res_text)
        if isinstance(parsed, dict) and "is_correct" in parsed:
            return task, parsed
    except Exception as e:
        log.error(f"Error on {task['id']}: {e}")
    return task, None

def main():
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, answer_type, tags, distractor_meta, answer_options, answer_options_latex
        FROM tasks_master
        WHERE verification_status = 'pending'
        ORDER BY id;
    """)
    tasks = cur.fetchall()
    log.info(f"Loaded {len(tasks)} pending tasks for parallel SmartVerify arbitration.")

    db_lock = threading.Lock()
    verified_cnt = 0
    rejected_cnt = 0
    error_cnt = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_task, t) for t in tasks]
        for f in as_completed(futures):
            task, res = f.result()
            tid = task['id']
            if not res:
                error_cnt += 1
                log.warning(f"[{tid}] Failed to get valid LLM response.")
                continue

            with db_lock:
                tags = dict(task['tags'] or {})
                if res.get("is_correct"):
                    cal_raw = res.get("correct_answer_latex", "").strip()
                    if not cal_raw.startswith("$") and not cal_raw.endswith("$") and cal_raw:
                        cal = f"${cal_raw}$"
                    else:
                        cal = cal_raw or task['correct_answer_latex'] or f"${task['correct_answer']}$"

                    # Дистракторы
                    dms = res.get("distractors", [])
                    clean_dms = []
                    for d in dms:
                        vl_raw = d.get("value_latex", "").strip()
                        if not vl_raw.startswith("$") and not vl_raw.endswith("$") and vl_raw:
                            vl = f"${vl_raw}$"
                        else:
                            vl = vl_raw or d.get("value", "")
                        clean_dms.append({
                            "value": d.get("value", ""),
                            "value_latex": vl,
                            "error_type": "ai_generated",
                            "error_logic": d.get("error_logic", ""),
                            "explanation": d.get("explanation", d.get("error_logic", "")),
                            "plausibility": 0.75
                        })
                    if not clean_dms:
                        clean_dms = _json_list(task['distractor_meta'])

                    # Проверяем качество LaTeX
                    ql = task['question_latex'] or task['question_text']
                    issues, req = final_display_issues(task['question_text'], ql, task['correct_answer'], cal, clean_dms, task['answer_options'], task['answer_options_latex'])
                    l_status = latex_status_from_issues(issues, req)

                    tags["smart_verify_status"] = "verified_match"
                    tags["reverified_by"] = "deepseek_arbitration"
                    tags["verification_explanation"] = res.get("explanation", "")
                    ans_type = res.get("real_answer_type") or task['answer_type']

                    cur.execute("""
                        UPDATE tasks_master
                        SET verification_status = 'verified',
                            latex_status = %s,
                            correct_answer_latex = %s,
                            distractor_meta = %s,
                            answer_type = %s,
                            tags = %s,
                            updated_at = NOW()
                        WHERE id = %s;
                    """, (l_status, cal, json.dumps(clean_dms, ensure_ascii=False), ans_type, json.dumps(tags, ensure_ascii=False), tid))
                    conn.commit()
                    verified_cnt += 1
                    log.info(f"[{verified_cnt}/{len(tasks)}] ✅ VERIFIED: {tid} | Type: {ans_type} | LaTeX: {l_status}")
                else:
                    tags["smart_verify_status"] = "rejected"
                    tags["rejection_reason"] = res.get("explanation", "deepseek_mathematical_contradiction")
                    cur.execute("""
                        UPDATE tasks_master
                        SET verification_status = 'rejected',
                            tags = %s,
                            updated_at = NOW()
                        WHERE id = %s;
                    """, (json.dumps(tags, ensure_ascii=False), tid))
                    conn.commit()
                    rejected_cnt += 1
                    log.warning(f"[{rejected_cnt}/{len(tasks)}] 🚫 REJECTED: {tid} | Reason: {tags['rejection_reason'][:60]}")

    conn.close()
    log.info(f"🏁 ALL DONE! Total verified: {verified_cnt}, Rejected: {rejected_cnt}, Errors: {error_cnt}")

if __name__ == '__main__':
    main()
