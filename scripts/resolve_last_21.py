import os
import sys
import json
import re
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model
from scripts.backfill_latex_deepseek import (
    final_display_issues,
    latex_status_from_issues,
    _json_list
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("resolve_last_21")

SYSTEM_PROMPT = """Ты — ведущий математик-эксперт и ИИ-верификатор школьной образовательной платформы.
Твоя задача — строго и профессионально проверить математическую корректность задачи, эталонного ответа и сгенерировать 3 качественных дистрактора.

ВНИМАНИЕ ПО ФОРМАТИРОВАНИЮ:
1. Пиши формулы в обычном тексте, но для JSON экранируй обратные слэши \\\\frac, \\\\sqrt.
2. Не используй невалидные символы внутри строк JSON.

Верни строго JSON:
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

def robust_parse_json(text: str):
    if not text:
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
    if m:
        t = m.group(1).strip()
    
    # 1. Попытка стандартного парсинга
    try:
        return json.loads(t, strict=False)
    except Exception:
        pass
        
    # 2. Экранирование всех одиночных \ кроме \", \\, \/, \b, \f, \n, \r, \t, \u
    fixed_t = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', t)
    try:
        return json.loads(fixed_t, strict=False)
    except Exception:
        pass

    # 3. Извлечение по регулярным выражениям если JSON обрезан
    try:
        is_cor = "true" in re.search(r'"is_correct"\s*:\s*(true|false)', t, re.I).group(1).lower()
        cal_m = re.search(r'"correct_answer_latex"\s*:\s*"([^"]*)"', t)
        cal = cal_m.group(1) if cal_m else ""
        expl_m = re.search(r'"explanation"\s*:\s*"([^"]*)"', t)
        expl = expl_m.group(1) if expl_m else "Verified by mathematical arbitration"
        
        # Извлекаем дистракторы
        distractors = []
        d_blocks = re.findall(r'\{\s*"value"\s*:\s*"([^"]*)".*?"error_logic"\s*:\s*"([^"]*)"', t, re.DOTALL)
        for val, err in d_blocks:
            distractors.append({
                "value": val,
                "value_latex": val,
                "error_type": "ai_generated",
                "error_logic": err,
                "explanation": err,
                "plausibility": 0.75
            })
            
        return {
            "is_correct": is_cor,
            "real_answer_type": "expression",
            "correct_answer_latex": cal,
            "explanation": expl,
            "distractors": distractors
        }
    except Exception as e:
        log.error(f"Fallback regex parse failed: {e}")
        
    return None

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
    log.info(f"Loaded {len(tasks)} remaining pending tasks.")

    verified = 0
    rejected = 0

    for t in tasks:
        tid = t['id']
        prompt = f"УСЛОВИЕ ЗАДАЧИ:\n{t['question_text']}\n\nИСХОДНЫЙ ОТВЕТ:\n{t['correct_answer']}"
        res_text = call_deepseek(prompt, system_prompt=SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.1)
        res = robust_parse_json(res_text)
        
        if not res:
            log.warning(f"Could not parse response for {tid}")
            continue

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
            verified += 1
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
            rejected += 1
            log.warning(f"🚫 REJECTED: {tid}")

    conn.close()
    log.info(f"DONE. Verified: {verified}, Rejected: {rejected}")

if __name__ == '__main__':
    main()
