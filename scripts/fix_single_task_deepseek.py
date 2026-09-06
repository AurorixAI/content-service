#!/usr/bin/env python3
"""
Fix a single task's LaTeX via DeepSeek:
  - question_text, question_latex
  - correct_answer, correct_answer_latex
  - distractor_meta[].value  AND  distractor_meta[].value_latex
  - distractor_meta[].error_logic  AND  distractor_meta[].explanation

Usage:
  python3 scripts/fix_single_task_deepseek.py --task-id G10_TB_1_1_4_3 [--execute]
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('APP_ENV', 'production')

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

import psycopg2
from src.pipeline.deepseek_client import call_deepseek

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fix_single_task")

# ──────────────────────────────────────────
# PROMPT: тот же улучшенный промпт
# ──────────────────────────────────────────
PROMPT_PREFIX = """\
You are an expert mathematical LaTeX formatter for a high-school mathematics platform.
Your task is to re-format the provided text into 100% valid, professional KaTeX/LaTeX formatting.

RULES:
1. Use $...$ delimiters for inline math (e.g., $y = y(x)$, $x^3$, $e^{-4x}$, $y'' = 16y$).
2. Use \\dfrac{a}{b} for fractions (NOT \\frac). Use \\lim_{x\\to a} for limits. Use \\sqrt{a} for roots.
3. Keep Russian prose outside $. Ensure proper spacing between Russian words and $ delimiters.
4. Fix any typos: ,\\f -> , \\left; stuck words like y(x)является -> y(x) является.
5. CRITICAL: Output ONLY the final formatted string. No markdown, no code blocks, no quotes.

Input: """


def fmt(text: str) -> str:
    if not text or not text.strip():
        return text
    prompt = PROMPT_PREFIX + text.strip() + "\nOutput: "
    try:
        res = call_deepseek(prompt, temperature=0.0, max_tokens=1000)
        res = res.strip()
        # Strip markdown fences
        if res.startswith("```"):
            parts = res.split("```")
            res = parts[1] if len(parts) >= 2 else res
            if res.startswith("latex") or res.startswith("math"):
                res = res[res.index("\n")+1:]
        # Strip surrounding quotes
        if (res.startswith('"') and res.endswith('"')) or (res.startswith("'") and res.endswith("'")):
            res = res[1:-1]
        return res.strip()
    except Exception as e:
        log.error("DeepSeek error: %s", e)
        return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True, help="Task id, e.g. G10_TB_1_1_4_3")
    ap.add_argument("--execute", action="store_true", help="Actually write to DB")
    args = ap.parse_args()

    conn = psycopg2.connect(
        dbname="algo_content", user="algo", password="algo_password",
        host="127.0.0.1", port=5434
    )
    cur = conn.cursor()

    cur.execute(
        """SELECT id, question_text, question_latex, correct_answer, correct_answer_latex, distractor_meta
           FROM tasks_master WHERE id = %s""",
        (args.task_id,)
    )
    row = cur.fetchone()
    if not row:
        log.error("Task %s not found!", args.task_id)
        return

    tid, qt, ql, ca, cal, dmeta = row

    log.info("=== Processing: %s ===", tid)

    # ── 1. Question ──────────────────────────────────
    log.info("Formatting question_text / question_latex …")
    new_qt = fmt(qt or "")
    log.info("  OLD: %s", repr(qt))
    log.info("  NEW: %s", repr(new_qt))

    # ── 2. Correct answer ────────────────────────────
    log.info("Formatting correct_answer / correct_answer_latex …")
    new_ca = fmt(ca or "")
    log.info("  OLD: %s", repr(ca))
    log.info("  NEW: %s", repr(new_ca))

    # ── 3. Distractors ───────────────────────────────
    new_dmeta = []
    if dmeta:
        for i, d in enumerate(dmeta):
            log.info("Formatting distractor %d …", i)

            old_val = str(d.get("value") or "").strip()
            new_val = fmt(old_val) if old_val else old_val
            log.info("  value OLD: %s", repr(old_val))
            log.info("  value NEW: %s", repr(new_val))

            old_el = str(d.get("error_logic") or "").strip()
            new_el = fmt(old_el) if old_el else old_el
            log.info("  error_logic OLD: %s", repr(old_el))
            log.info("  error_logic NEW: %s", repr(new_el))

            old_exp = str(d.get("explanation") or "").strip()
            new_exp = fmt(old_exp) if old_exp else old_exp
            log.info("  explanation OLD: %s", repr(old_exp))
            log.info("  explanation NEW: %s", repr(new_exp))

            d["value"]       = new_val
            d["value_latex"] = new_val   # canonical rendered form
            d["error_logic"] = new_el
            d["explanation"] = new_exp
            new_dmeta.append(d)
    else:
        new_dmeta = dmeta

    # ── 4. Write to DB ───────────────────────────────
    if args.execute:
        cur.execute(
            """UPDATE tasks_master
               SET question_text       = %s,
                   question_latex      = %s,
                   correct_answer      = %s,
                   correct_answer_latex= %s,
                   distractor_meta     = %s,
                   updated_at          = NOW()
               WHERE id = %s""",
            (
                new_qt, new_qt,
                new_ca, new_ca,
                json.dumps(new_dmeta, ensure_ascii=False),
                tid
            )
        )
        conn.commit()
        log.info("✅ DB updated for %s", tid)
    else:
        log.info("DRY RUN — pass --execute to save to DB.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
