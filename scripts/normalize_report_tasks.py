import asyncio
import psycopg2
import json
import sys
import os

# Add content-service to sys.path
sys.path.insert(0, '/Users/arslan/Desktop/ALGO/content-service')

from scripts.backfill_latex_deepseek import format_latex

async def normalize_report_tasks():
    diag_conn = psycopg2.connect(dbname='algo_diagnostic', user='algo', password='algo_password', host='127.0.0.1', port=5433)
    diag_cur = diag_conn.cursor()

    content_conn = psycopg2.connect(dbname='algo_content', user='algo', password='algo_password', host='127.0.0.1', port=5434)
    content_cur = content_conn.cursor()

    # Collect task IDs from reports and answers
    diag_cur.execute("SELECT DISTINCT task_id FROM diag_answers WHERE task_id IS NOT NULL AND task_id != '';")
    tids = [r[0] for r in diag_cur.fetchall()]

    print(f"Found {len(tids)} distinct task IDs from diag_answers.")

    sem = asyncio.Semaphore(5)
    normalized_count = 0

    for idx, tid in enumerate(tids, 1):
        content_cur.execute("SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, distractor_meta FROM tasks_master WHERE id = %s;", (tid,))
        row = content_cur.fetchone()
        if not row:
            continue

        tid_db, q_text, q_latex, c_ans, c_ans_latex, distractor_meta_raw = row
        dm_list = distractor_meta_raw if isinstance(distractor_meta_raw, list) else (json.loads(distractor_meta_raw or '[]') if isinstance(distractor_meta_raw, str) else [])

        # Check if question needs LaTeX normalization (e.g. array, missing $, \\neq, \\tgx, \\sinx, \\dfracpi)
        raw_target_q = q_text or q_latex or ""
        needs_q = (
            "array" in raw_target_q or
            "\\sinx" in raw_target_q or
            "\\tgx" in raw_target_q or
            "neq" in raw_target_q or
            "dfracpi" in raw_target_q or
            ("y =" in raw_target_q and "$" not in raw_target_q) or
            ("f(x) =" in raw_target_q and "$" not in raw_target_q) or
            "\\left\\{" in raw_target_q
        )

        new_q_latex = q_latex
        if needs_q or not q_latex:
            res_q = await format_latex(raw_target_q, sem)
            if res_q and res_q.get("canonical"):
                new_q_latex = res_q["canonical"]

        # Check correct answer
        raw_target_c = c_ans_latex or c_ans or ""
        needs_c = (
            "\\sinx" in raw_target_c or
            "\\tgx" in raw_target_c or
            "neq" in raw_target_c or
            "dfracpi" in raw_target_c or
            "\\left\\{" in raw_target_c
        )

        new_c_latex = c_ans_latex or c_ans
        if (needs_c or not c_ans_latex) and raw_target_c:
            res_c = await format_latex(raw_target_c, sem)
            if res_c and res_c.get("canonical"):
                new_c_latex = res_c["canonical"]

        # Check distractor_meta values & explanations
        new_dm = []
        dm_changed = False
        for dm in dm_list:
            if isinstance(dm, dict):
                dm_copy = dict(dm)
                val_target = dm_copy.get("value_latex") or dm_copy.get("value") or ""
                if val_target and ("\\sinx" in val_target or "\\tgx" in val_target or "neq" in val_target or "dfracpi" in val_target or "array" in val_target):
                    res_val = await format_latex(val_target, sem)
                    if res_val and res_val.get("canonical"):
                        dm_copy["value_latex"] = res_val["canonical"]
                        dm_changed = True
                
                exp_target = dm_copy.get("explanation") or dm_copy.get("error_logic") or ""
                if exp_target and ("\\sinx" in exp_target or "\\tgx" in exp_target or "neq" in exp_target or "dfracpi" in exp_target or "array" in exp_target):
                    res_exp = await format_latex(exp_target, sem)
                    if res_exp and res_exp.get("canonical"):
                        dm_copy["explanation"] = res_exp["canonical"]
                        dm_changed = True
                
                new_dm.append(dm_copy)
            else:
                new_dm.append(dm)

        # Update DB if anything changed
        if new_q_latex != q_latex or new_c_latex != c_ans_latex or dm_changed:
            content_cur.execute(
                "UPDATE tasks_master SET question_latex = %s, correct_answer_latex = %s, distractor_meta = %s, latex_status = 'verified' WHERE id = %s;",
                (new_q_latex, new_c_latex, json.dumps(new_dm, ensure_ascii=False), tid)
            )
            normalized_count += 1
            print(f"[{idx}/{len(tids)}] Updated Task {tid} in tasks_master.", flush=True)

    content_conn.commit()
    print(f"Successfully normalized {normalized_count} tasks in tasks_master!", flush=True)

if __name__ == "__main__":
    asyncio.run(normalize_report_tasks())
