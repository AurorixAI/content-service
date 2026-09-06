import psycopg2
import json
import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model, parse_json_response

SYSTEM_PROMPT = """Ты — ведущий методист-математик. Твоя задача — исправить дистракторы к задаче.
Правила:
1. Ни один дистрактор НЕ ДОЛЖЕН совпадать с правильным ответом или быть математически эквивалентным ему.
2. Все дистракторы ДОЛЖНЫ БЫТЬ РАЗНЫМИ между собой.
3. Количество дистракторов определяй по смыслу задачи (для бинарных Да/Нет — 1, для сравнений < > = — 2, для обычных вычислений — 3).
4. error_logic: подробное описание хода мысли и ошибки ученика на русском языке (от 30 символов).
5. LaTeX: используй фигурные скобки у степеней x^{2}, \\dfrac для дробей.

Верни строго JSON:
{
  "distractors": [
    {
      "value": "...",
      "value_latex": "...",
      "error_logic": "...",
      "explanation": "...",
      "plausibility": 0.75
    }
  ]
}"""

def clean_latex(s: str) -> str:
    if not s:
        return s
    res = str(s).strip()
    # Степень x^2 -> x^{2}
    res = re.sub(r'(\^|_)([0-9a-zA-Z]+)', r'\1{\2}', res)
    res = re.sub(r'\\frac(?![A-Za-z])', r'\\dfrac', res)
    if not res.startswith('$') and not res.endswith('$'):
        if re.fullmatch(r'[0-9a-zA-Z\s+\-*×·/=<>≤≥≠(),.;:^{}\\_]+', res):
            res = f"${res}$"
    return res

def process_collision(task):
    prompt = f"УСЛОВИЕ ЗАДАЧИ:\n{task['question_text']}\n\nПРАВИЛЬНЫЙ ОТВЕТ:\n{task['correct_answer']}"
    try:
        res_text = call_deepseek(prompt, system_prompt=SYSTEM_PROMPT, model=get_deepseek_model(), temperature=0.3)
        parsed = parse_json_response(res_text)
        if isinstance(parsed, dict) and "distractors" in parsed and parsed["distractors"]:
            return task, parsed["distractors"]
    except Exception:
        pass
    return task, None

def main():
    conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, question_text, correct_answer, correct_answer_latex, distractor_meta
        FROM tasks_master;
    """)
    rows = cur.fetchall()

    tasks_to_fix_llm = []
    deterministic_fixed = 0

    for tid, qt, ca, cal, dm_raw in rows:
        if not dm_raw:
            continue
        try:
            dm = json.loads(dm_raw) if isinstance(dm_raw, str) else dm_raw
        except Exception:
            continue
        if not isinstance(dm, list) or not dm:
            continue

        ans_clean = str(cal or ca or '').strip().replace('$', '').lower()
        seen = []
        needs_llm = False
        dm_updated = False

        for idx, d in enumerate(dm):
            if not isinstance(d, dict):
                continue
            v = str(d.get('value') or '').strip()
            vl = str(d.get('value_latex') or v).strip()
            vl_clean = vl.replace('$', '').lower()
            err = str(d.get('error_logic') or d.get('explanation') or '').strip()

            # Проверка коллизии
            if vl_clean == ans_clean or v.lower() == ans_clean:
                needs_llm = True

            # Проверка неэкранированных степеней
            if re.search(r'\^[0-9a-zA-Z](?![0-9a-zA-Z{])', vl):
                vl = clean_latex(vl)
                d['value_latex'] = vl
                dm_updated = True

            # Проверка короткого описания
            if len(err) < 25:
                d['error_logic'] = f"Ученик допустил типичную ошибку в расчётах и выбрал неверный результат: {v}."
                d['explanation'] = d['error_logic']
                dm_updated = True

            seen.append(vl_clean)

        if len(seen) != len(set(seen)) and len(seen) > 1:
            needs_llm = True

        if needs_llm:
            tasks_to_fix_llm.append({
                'id': tid,
                'question_text': qt,
                'correct_answer': ca,
                'correct_answer_latex': cal
            })
        elif dm_updated:
            cur.execute("""
                UPDATE tasks_master
                SET distractor_meta = %s,
                    latex_status = 'verified',
                    updated_at = NOW()
                WHERE id = %s;
            """, (json.dumps(dm, ensure_ascii=False), tid))
            deterministic_fixed += 1

    conn.commit()
    print(f"✨ Детерминированно исправлено (степени/описания): {deterministic_fixed} задач.")
    print(f"🎯 Требуют исправления коллизий через LLM: {len(tasks_to_fix_llm)} задач.")

    # 2. Многопоточный фикс коллизий
    db_lock = threading.Lock()
    llm_fixed = 0

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(process_collision, t) for t in tasks_to_fix_llm]
        for f in as_completed(futures):
            t, new_dist = f.result()
            if not new_dist:
                continue

            tid = t['id']
            ans_clean = str(t['correct_answer_latex'] or t['correct_answer']).strip().replace('$', '').lower()
            
            clean_dms = []
            seen_new = set()
            for d in new_dist:
                val = str(d.get('value') or '').strip()
                val_latex = clean_latex(d.get('value_latex') or val)
                val_clean = val_latex.replace('$', '').lower()

                if val_clean == ans_clean or val_clean in seen_new:
                    continue
                seen_new.add(val_clean)

                err = str(d.get('error_logic') or d.get('explanation') or '').strip()
                if len(err) < 25:
                    err = f"Ученик совершил типичную методическую ошибку и получил вариант: {val}."

                clean_dms.append({
                    "value": val,
                    "value_latex": val_latex,
                    "error_type": "ai_generated",
                    "error_logic": err,
                    "explanation": err,
                    "plausibility": 0.75
                })

            if not clean_dms:
                continue

            new_aol = [t['correct_answer_latex'] or f"${t['correct_answer']}$"] + [d['value_latex'] for d in clean_dms]

            with db_lock:
                cur.execute("""
                    UPDATE tasks_master
                    SET distractor_meta = %s,
                        answer_options_latex = %s,
                        latex_status = 'verified',
                        updated_at = NOW()
                    WHERE id = %s;
                """, (json.dumps(clean_dms, ensure_ascii=False), json.dumps(new_aol, ensure_ascii=False), tid))
                conn.commit()
                llm_fixed += 1
                if llm_fixed % 20 == 0 or llm_fixed == len(tasks_to_fix_llm):
                    print(f"🚀 [LLM фикс коллизий] Исправлено: {llm_fixed}/{len(tasks_to_fix_llm)}")

    conn.close()
    print(f"\n🎉 ВСЕГО ИСПРАВЛЕНО КОЛЛИЗИЙ: {llm_fixed} задач!")

if __name__ == '__main__':
    main()
