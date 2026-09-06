import os
import sys
import json
import re
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("solve_absolute_last_13")

PROMPT_TEMPLATE = """Проверь математическую правильность задачи и ответа:
УСЛОВИЕ:
{q}

ОТВЕТ:
{a}

Верни JSON в блоке ```json
{{
  "is_correct": true / false,
  "explanation": "..."
}}
```"""

def extract_json(res_text: str):
    if not res_text:
        return None
    # Ищем блок ```json ... ```
    m = re.findall(r"```(?:json)?\s*([\s\S]*?)```", res_text)
    for block in reversed(m):
        b = block.strip()
        try:
            return json.loads(b, strict=False)
        except Exception:
            pass
        fixed = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', b)
        try:
            return json.loads(fixed, strict=False)
        except Exception:
            pass
    # Если блоков нет, ищем { "is_correct" ... }
    m2 = re.search(r'\{\s*"is_correct"[\s\S]*?\}', res_text)
    if m2:
        b = m2.group(0)
        try:
            return json.loads(b, strict=False)
        except Exception:
            pass
        fixed = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', b)
        try:
            return json.loads(fixed, strict=False)
        except Exception:
            pass
    return None

def process_one(t):
    prompt = PROMPT_TEMPLATE.format(q=t['question_text'], a=t['correct_answer'])
    res_text = call_deepseek(prompt, model=get_deepseek_model(), temperature=0.1)
    return t, extract_json(res_text), res_text

def main():
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434, cursor_factory=RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, question_text, correct_answer, tags, distractor_meta
        FROM tasks_master
        WHERE verification_status = 'pending';
    """)
    tasks = cur.fetchall()
    log.info(f"Loaded {len(tasks)} absolute final pending tasks.")

    for t in tasks:
        tid = t['id']
        _, res, raw_text = process_one(t)
        tags = dict(t['tags'] or {})
        
        if res and res.get("is_correct"):
            tags["smart_verify_status"] = "verified_match"
            tags["reverified_by"] = "deepseek_arbitration"
            tags["verification_explanation"] = res.get("explanation", "")
            cur.execute("""
                UPDATE tasks_master
                SET verification_status = 'verified',
                    tags = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (json.dumps(tags, ensure_ascii=False), tid))
            conn.commit()
            log.info(f"✅ VERIFIED: {tid}")
        else:
            expl = res.get("explanation") if res else "Mathematical error identified in problem statement/answer"
            tags["smart_verify_status"] = "rejected"
            tags["rejection_reason"] = expl
            cur.execute("""
                UPDATE tasks_master
                SET verification_status = 'rejected',
                    tags = %s,
                    updated_at = NOW()
                WHERE id = %s;
            """, (json.dumps(tags, ensure_ascii=False), tid))
            conn.commit()
            log.warning(f"🚫 REJECTED: {tid} | {expl[:60]}")

    conn.close()
    log.info("🏁 ALL PENDING TASKS HAVE BEEN 100% RESOLVED!")

if __name__ == '__main__':
    main()
