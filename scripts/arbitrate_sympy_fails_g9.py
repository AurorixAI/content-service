from src.core.database import get_db
from src.pipeline.deepseek_client import call_deepseek_structured, get_deepseek_model
from src.pipeline.smart_verify_common import run_distractor_only_pipeline
from src.pipeline.answer_sympy_gate import to_answer_latex
from src.schemas.smart_verify import TextVerifyResponse
from sqlalchemy import create_engine, text
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("arbitrate_sympy")

def build_arbitration_prompt(question: str, db_answer: str, llm_answer: str) -> str:
    llm_ans_str = llm_answer if llm_answer else "(пусто)"
    return (
        "Ты — профессиональный математик-арбитр. Твоя задача — сравнить два ответа к школьной задаче по математике и определить, эквивалентны ли они, а также выбрать лучший математический формат.\n\n"
        f"Задача:\n{question}\n\n"
        f"Ответ A (из базы/учебника): {db_answer}\n"
        f"Ответ B (вычисленный моделью): {llm_ans_str}\n\n"
        "Верни строго JSON со следующими полями:\n"
        "- absolute_correct_answer: строка 'true', если Ответ A и Ответ B математически эквивалентны. "
        "Если Ответ B пуст ((пусто)), самостоятельно реши задачу по ее условию. Если Ответ A является математически верным и точным решением, также верни 'true', иначе 'false'.\n"
        "- step_by_step_solution: чистый математический ответ для базы данных (без слов 'Ответ', без русских букв, без скобок вокруг всего выражения, без знака ±).\n"
        "  Пример: вместо 'x = ±2' пиши 'x = 2; x = -2'. Вместо 'x = 2 или x = 3' пиши 'x = 2; x = 3'. Координаты пиши через точку с запятой, например '(2; 5); (-2; 5)'.\n"
        "- confidence: краткое математическое обоснование, почему они эквивалентны или почему Ответ A верен."
    )

def process_task(engine, row):
    task_id, q_text, db_ans, llm_ans, atype, dist_meta, tags = row
    tags = tags or {}
    
    prompt = build_arbitration_prompt(q_text, db_ans, llm_ans or "")
    try:
        res_llm = call_deepseek_structured(prompt, TextVerifyResponse, model=get_deepseek_model(), temperature=0.0)
        equivalent = res_llm.absolute_correct_answer.strip().lower() == "true"
        best_ans = res_llm.step_by_step_solution.strip()
        explanation = res_llm.confidence
        
        if equivalent:
            log.info(f"Task {task_id}: EQUIVALENT. Best answer: '{best_ans}'")
            
            # 1. Run distractor generation pipeline
            res_pipeline = run_distractor_only_pipeline(
                task_id=task_id,
                question=q_text,
                correct_answer=best_ans,
                answer_type=atype,
                distractor_meta=dist_meta,
                tags=tags
            )
            
            new_tags = res_pipeline.get("tags", tags)
            new_tags["smart_verify_status"] = "verified_match" if best_ans == db_ans else "verified_corrected"
            new_tags["answer_locked"] = True
            new_tags["answer_source"] = "computed"
            new_tags["sympy_verified"] = False
            new_tags["arbitrated"] = True
            new_tags["step_by_step_solution"] = explanation
            new_tags.pop("smart_verify_error", None)
            new_tags.pop("quarantine_v3_needs_review", None)
            new_tags["quarantine_v3_processed"] = True
            
            new_ans = res_pipeline.get("correct_answer", best_ans)
            new_ans_latex = res_pipeline.get("correct_answer_latex", "")
            if not new_ans_latex and new_ans:
                new_ans_latex = to_answer_latex(new_ans, atype)
                
            new_dmeta = res_pipeline.get("distractor_meta", dist_meta)
            
            # 2. Write updates back to DB
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        UPDATE tasks_master
                        SET correct_answer = :ans,
                            correct_answer_latex = :ans_latex,
                            distractor_meta = CAST(:dmeta AS jsonb),
                            tags = CAST(:tags AS jsonb),
                            verification_status = 'verified'
                        WHERE id = :id
                    """),
                    {
                        "id": task_id,
                        "ans": new_ans,
                        "ans_latex": new_ans_latex,
                        "dmeta": json.dumps(new_dmeta, ensure_ascii=False),
                        "tags": json.dumps(new_tags, ensure_ascii=False)
                    }
                )
                conn.commit()
            log.info(f"Task {task_id} successfully verified and updated.")
            return True
        else:
            log.warning(f"Task {task_id}: NOT EQUIVALENT. Explanation: {explanation}")
            return False
    except Exception as e:
        log.error(f"Error processing task {task_id}: {e}")
        return False

def main():
    from src.core.config import get_settings
    s = get_settings()
    engine = create_engine(s.database_url)
    
    tb_prefix = "G9_TB_%"
    with engine.connect() as conn:
        res = conn.execute(
            text("""
                SELECT id, question_text, correct_answer, 
                       COALESCE(tags->>'quarantine_v3_ai_answer', tags->>'answer_llm_prose') as llm_ans, 
                       answer_type, distractor_meta, tags
                FROM tasks_master
                WHERE id LIKE :tb_prefix
                  AND (
                      tags->>'quarantine_v3_needs_review' = 'true'
                      OR tags->>'smart_verify_status' IN ('failed_at_llm', 'failed_at_sympy', 'needs_human_review')
                  )
                ORDER BY id
            """),
            {"tb_prefix": tb_prefix}
        )
        rows = res.fetchall()
        
    log.info(f"Found {len(rows)} tasks failed at SymPy to process.")
    
    # Process using ThreadPoolExecutor for concurrency
    success_count = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_task, engine, row) for row in rows]
        for f in futures:
            if f.result():
                success_count += 1
                
    log.info(f"Done. Successfully verified and closed {success_count} out of {len(rows)} failed_at_sympy tasks.")

if __name__ == "__main__":
    main()
