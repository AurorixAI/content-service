#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, "/app")
os.environ.setdefault('APP_ENV', 'production')

from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.deepseek_client import call_deepseek as _call_deepseek

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_latex_deepseek")

PROMPT = """You are a mathematical text formatter.
Your task is to wrap all math expressions, numbers, and variables in the provided text with LaTeX delimiters `$`...`$`.
DO NOT change, solve, or simplify any math expressions. DO NOT translate or modify the Russian text.
Only wrap math components. 
CRITICAL RULE: Return ONLY the final formatted text. Do not return JSON. Do not wrap in arrays or objects. Do not use Markdown code blocks. Just the raw formatted text string WITHOUT surrounding quotes.

For example:
Input: Длина отрезка AB равна 5.5 см, найдите x + y.
Output: Длина отрезка $AB$ равна $5.5$ см, найдите $x + y$.

Input: {text}
Output: """

def call_deepseek_latex(prompt: str) -> str:
    """Use existing Azure DeepSeek client."""
    return _call_deepseek(prompt, temperature=0.0, max_tokens=500)

async def format_latex(text_str: str) -> str:
    if not text_str or not text_str.strip():
        return text_str
    try:
        prompt = PROMPT.format(text=text_str.strip())
        # Run blocking HTTP call in thread
        res = await asyncio.to_thread(call_deepseek_latex, prompt)
        res = res.strip()
        # Clean markdown codeblocks
        if res.startswith("```") and res.endswith("```"):
            res = "\n".join(res.split("\n")[1:-1]).strip()
        if res.startswith('"') and res.endswith('"'):
            res = res[1:-1].strip()
        if res.startswith("'") and res.endswith("'"):
            res = res[1:-1].strip()
        return res
    except Exception as e:
        log.error("DeepSeek failed: %s", e)
        return text_str

async def process_task(tid, qt, ans, dmeta_json):
    new_qt = await format_latex(qt) if qt else qt
    new_ans = await format_latex(ans) if ans else ans
    
    new_dmeta = []
    if dmeta_json:
        try:
            dmeta = json.loads(dmeta_json) if isinstance(dmeta_json, str) else dmeta_json
            for d in dmeta:
                if isinstance(d, dict) and d.get("value"):
                    val = str(d["value"]).strip()
                    if val:
                        d["value_latex"] = await format_latex(val)
                new_dmeta.append(d)
        except Exception as e:
            log.error("Failed to parse dmeta for %s: %s", tid, e)
            new_dmeta = dmeta_json
    return tid, new_qt, new_ans, new_dmeta

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--class-level", type=int, help="Grade filter")
    ap.add_argument("--limit", type=int, default=0, help="Max tasks to process")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    s = get_settings()
    engine = create_engine(s.database_url)

    where_clause = "tb.class_level = :lvl" if args.class_level else "tb.class_level BETWEEN 5 AND 8"

    with engine.connect() as c:
        # Target: new G9 sections + all tasks changed/verified in current session
        rows = c.execute(text(f"""
            SELECT tm.id, tm.question_text, tm.correct_answer, tm.distractor_meta
            FROM tasks_master tm
            JOIN textbook_toc toc ON toc.id=tm.toc_id
            JOIN textbooks tb ON tb.textbook_id=toc.textbook_id
            WHERE {where_clause}
              AND tm.is_active = true
              AND (
                -- New sections (§31, ДГ5, ЗПТ, УПК)
                toc.number = ANY(ARRAY['31','ДГ5','ЗПТ','УПК'])
                -- Tasks verified/corrected in current session
                OR tm.tags->>'smart_verify_status' = 'verified_corrected'
                -- Tasks with LLM-generated distractors
                OR tm.distractor_meta->0->>'source' IN ('llm','llm_universal','llm_manual','llm_corrected')
              )
            ORDER BY tm.id DESC
        """), {"lvl": args.class_level}).fetchall()

    if args.limit:
        rows = rows[:args.limit]

    log.info("Found %d tasks remaining to process", len(rows))
    if not args.execute:
        log.info("DRY RUN. Pass --execute to save to DB.")
        
    concurrency = 10 # DeepSeek API limits
    semaphore = asyncio.Semaphore(concurrency)
    
    async def bounded_process(row):
        async with semaphore:
            return await process_task(row[0], row[1], row[2], row[3])

    tasks = [bounded_process(row) for row in rows]
    
    batch_size = 30
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i+batch_size]
        results = await asyncio.gather(*batch)
        
        if args.execute:
            with engine.begin() as conn:
                for tid, ql, cal, dmeta in results:
                    conn.execute(text("""
                        UPDATE tasks_master
                        SET question_latex = :ql,
                            correct_answer_latex = :cal,
                            distractor_meta = :dmeta,
                            updated_at = NOW()
                        WHERE id = :id
                    """), {
                        "ql": ql or "",
                        "cal": cal or "",
                        "dmeta": json.dumps(dmeta, ensure_ascii=False) if isinstance(dmeta, list) else dmeta,
                        "id": tid
                    })
        
        log.info("Processed batch %d/%d", i//batch_size + 1, (len(tasks)-1)//batch_size + 1)
        await asyncio.sleep(1) # Gentle rate limiting

if __name__ == "__main__":
    asyncio.run(main())
