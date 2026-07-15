import sys
import logging
import json
import os
from pathlib import Path

# Setup Azure Keys explicitly
os.environ["AZURE_MISTRAL_API_KEY"] = "ArSjteP5YKOUBTQRyB0fb1hXBgq2Sui96wZmoAou7eiHOdSPa0JHJQQJ99CFACYeBjFXJ3w3AAAAACOGxVOz"
os.environ["AZURE_MISTRAL_ENDPOINT"] = "https://arslan15114.services.ai.azure.com/providers/mistral/azure/ocr"
os.environ["AZURE_DEEPSEEK_API_KEY"] = "ArSjteP5YKOUBTQRyB0fb1hXBgq2Sui96wZmoAou7eiHOdSPa0JHJQQJ99CFACYeBjFXJ3w3AAAAACOGxVOz"
os.environ["AZURE_DEEPSEEK_ENDPOINT"] = "https://arslan15114.services.ai.azure.com/openai/v1/chat/completions"

logging.basicConfig(level=logging.INFO)

from src.pipeline.ocr import AzureMistralOCR
from src.pipeline.extraction import TaskExtractor
from src.pipeline.classification import SkeletonTextbookMapper
from src.pipeline.distractors import generate_distractors

def run():
    pdf_path = "/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf"
    
    # We will just dry-run on pages 9 to 10 (end of paragraph 1 where exercises are)
    start_page = 9
    end_page = 10
    
    print(f"--- 1. OCR pages {start_page}-{end_page} ---")
    ocr = AzureMistralOCR()
    text = ocr.process_pages(pdf_path, start_page, end_page)
    print(f"OCR extracted {len(text)} chars.")
    
    print(f"--- 2. Extraction ---")
    extractor = TaskExtractor()
    extracted_tasks = extractor.extract(text, "1. Действия над действительными числами")
    print(f"Extracted {len(extracted_tasks)} tasks.")
    
    # Take first 3 tasks to speed up the test
    test_tasks = extracted_tasks[:3]
    print(f"We will fully process the first {len(test_tasks)} tasks.")
    
    print(f"--- 3. Classification (Mapping) ---")
    sk_mapper = SkeletonTextbookMapper(9)
    mapped_sk = sk_mapper.map_batch(test_tasks)
    
    from src.pipeline.enrichment import AIAnswerSolver
    solver = AIAnswerSolver()
    
    print(f"--- 4. Solving & Distractors ---")
    final_tasks = []
    for task in mapped_sk:
        # Solve the task to get answer_raw
        solved_task = solver.solve(task)
        # Generate distractors
        final_task = generate_distractors(solved_task)
        final_tasks.append(final_task)
    
    import dataclasses
    # Dump to JSON
    out_file = "/app/dry_run_output.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([dataclasses.asdict(t) for t in final_tasks], f, ensure_ascii=False, indent=2)
        
    print(f"Dry run complete. Results saved to {out_file}")

if __name__ == "__main__":
    run()
