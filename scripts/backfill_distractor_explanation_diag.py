#!/usr/bin/env python3
"""
backfill_distractor_explanation.py

Backfill distractor_explanation / distractor_explanation_latex
for 110 error_patterns in diag_reports where it is null.

Run from content-service root:
  python3 scripts/backfill_distractor_explanation_diag.py
"""
import json
import os
import sys
import time

import psycopg2

# ── Env / client (same pattern as repair_all_distractors_and_latex.py) ────────
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('APP_ENV', 'production')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from src.pipeline.deepseek_client import call_deepseek, get_deepseek_model

# ── Diagnostic DB ─────────────────────────────────────────────────────────────
conn = psycopg2.connect(
    dbname='algo_diagnostic', user='algo',
    password='algo_password', host='127.0.0.1', port=5433
)
cur = conn.cursor()


PROMPT_TMPL = """Ты — педагогический математик. Ученик выбрал неверный ответ (дистрактор) в математической задаче.

Задача: {question}
Правильный ответ: {correct}
Ответ ученика (ошибочный дистрактор): {student}
Тема навыка: {skill}

Напиши персональное объяснение конкретной ошибки ученика. 2-3 предложения, 40-90 слов.
Объясни КОНКРЕТНО какую ошибку совершил ученик, выбрав этот ответ.
Используй LaTeX в формате $...$ для формул.
Верни ТОЛЬКО текст объяснения, без JSON, без заголовков, без лишних символов."""


def generate_explanation(ep: dict):  # -> str | None (py3.10+)
    q = ep.get('question_latex') or ep.get('question_text') or ''
    correct = ep.get('correct_answer_latex') or ep.get('correct_answer') or ''
    student = ep.get('student_answer_latex') or ep.get('student_answer') or ''
    skill = ep.get('skill_name_ru') or ''

    prompt = PROMPT_TMPL.format(
        question=q, correct=correct, student=student, skill=skill
    )

    try:
        res = call_deepseek(prompt, model=get_deepseek_model(), temperature=0.15)
        if res and isinstance(res, str) and len(res.strip()) > 20:
            return res.strip()
    except Exception as e:
        print(f"    ⛔ DeepSeek error: {e}")
    return None


def main():
    print(f"Model: {get_deepseek_model()}")

    cur.execute("SELECT id, report_json FROM diag_reports ORDER BY generated_at;")
    reports = cur.fetchall()

    total_filled = 0
    total_skipped = 0
    total_reports_updated = 0

    for report_id, rj in reports:
        if isinstance(rj, str):
            rj = json.loads(rj)
        if not rj or not isinstance(rj, dict):
            continue

        eps = rj.get('error_patterns', [])
        changed = False

        for ep in eps:
            if not isinstance(ep, dict):
                continue
            if ep.get('eval_category') != 'distractor':
                continue

            expl = ep.get('distractor_explanation') or ''
            if expl.strip() and len(expl.strip()) > 20:
                total_skipped += 1
                continue

            task_id = ep.get('task_id', '?')
            print(f"  ⚙️  {task_id}...", flush=True)
            new_expl = generate_explanation(ep)
            time.sleep(0.4)

            if new_expl:
                ep['distractor_explanation'] = new_expl
                ep['distractor_explanation_latex'] = new_expl
                changed = True
                total_filled += 1
                print(f"  ✅ {task_id}: {new_expl[:70]}...", flush=True)
            else:
                print(f"  ⚠️  {task_id}: failed — keeping null", flush=True)

        if changed:
            cur.execute(
                "UPDATE diag_reports SET report_json = %s WHERE id = %s;",
                (json.dumps(rj, ensure_ascii=False), report_id)
            )
            conn.commit()
            total_reports_updated += 1
            print(f"  💾 Report {report_id} saved", flush=True)

    # ── Final audit ───────────────────────────────────────────────────────────
    cur.execute("SELECT report_json FROM diag_reports;")
    null_after = 0
    for (rj_row,) in cur.fetchall():
        if isinstance(rj_row, str): rj_row = json.loads(rj_row)
        for ep in (rj_row or {}).get('error_patterns', []):
            if ep.get('eval_category') == 'distractor':
                if not (ep.get('distractor_explanation') or '').strip():
                    null_after += 1

    print(f"\n{'='*50}")
    print(f"✅ Сгенерировано:             {total_filled}")
    print(f"⏭️  Уже были (пропущено):      {total_skipped}")
    print(f"💾 Отчётов обновлено:          {total_reports_updated}")
    print(f"🔍 Null explanation после:     {null_after}")


if __name__ == '__main__':
    main()
