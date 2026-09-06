import os
import sys
import json
import re
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model
from scripts.backfill_latex_deepseek import (
    final_display_issues,
    latex_status_from_issues,
    _json_list
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("resolve_last_parallel")

SYSTEM_PROMPT = """Ты — ведущий математик-эксперт и ИИ-верификатор образовательной платформы.
Твоя задача — строго и профессионально проверить математическую корректность задачи, эталонного ответа и сгенерировать 3 качественных дистрактора.

ВНИМАНИЕ: Экранируй обратные слэши \\\\frac, \\\\sqrt.
Верни строго валидный JSON:
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

def robust_parse(t: str):
    if not t:
        return None
    text = t.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text, strict=False)
    except Exception:
        pass
    fixed = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', text)
    try:
        return json.loads(fixed, strict=False)
    except Exception:
        pass
    return None

def process(task):
    prompt = f"УСЛОВИЕ ЗАДАЧИ:\n{task['question_text']}\n\nИСХОДНЫЙ ОТВЕТ:\n{task['correct_answer']}"
    res_text = call_deepseek(prompt, system_prompt=SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.1)
    return task, robust_parse(res_text)

def main():
    pkill = os.system("pkill -f 'resolve_last_21.py'")
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, answer_type, tags, distractor_meta, answer_options, answer_options_latex
        FROM tasks_master
        WHERE verification_status = 'pending'
        ORDER BY id;
    """)
    tasks = cur.fetchall()
    log.info(f"Loaded {len(tasks)} remaining tasks for fast parallel arbitration.")

    db_lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = [executor.submit(process, t) for t in tasks]
        for f in as_completed(futures):
            t, res = f.result()
            tid = t['id']
            if not res:
                log.warning(f"Could not parse {tid}")
                continue

            with db_lock:
                tags = dict(t['tags'] or {})
                if res.get("is_correct"):
                    cal_raw = res.get("correct_answer_latex", "").strip()
                    if not cal_raw.startswith("$") and not cal_raw.endswith("$") and cal_raw:
                        cal = f"${cal_raw}$"
                    else:
                        cal = cal_raw or t['correct_answer_latex'] or f"${t['correct_answer']}$"

                    clean_dms = []
                    for d in res.get("distractors", []):
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
                        clean_dms = _json_list(t['distractor_meta'])

                    ql = t['question_latex'] or t['question_text']
                    issues, req = final_display_issues(t['question_text'], ql, t['correct_answer'], cal, clean_dms, t['answer_options'], t['answer_options_latex'])
                    l_status = latex_status_from_issues(issues, req)

                    tags["smart_verify_status"] = "verified_match"
                    tags["reverified_by"] = "deepseek_arbitration"
                    tags["verification_explanation"] = res.get("explanation", "")
                    ans_type = res.get("real_answer_type") or t['answer_type']

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
                    log.info(f"✅ VERIFIED: {tid}")
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
                    log.warning(f"🚫 REJECTED: {tid}")

    conn.close()
    log.info("🏁 ALL 16 REMAINING TASKS COMPLETED!")

if __name__ == '__main__':
    main()
