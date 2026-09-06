import sys
import logging
import asyncio
import os

os.environ["RESUME_FROM_PARAGRAPH"] = "0"
os.environ["AZURE_MISTRAL_API_KEY"] = "ArSjteP5YKOUBTQRyB0fb1hXBgq2Sui96wZmoAou7eiHOdSPa0JHJQQJ99CFACYeBjFXJ3w3AAAAACOGxVOz"
os.environ["AZURE_MISTRAL_ENDPOINT"] = "https://arslan15114.services.ai.azure.com/providers/mistral/azure/ocr"
os.environ["AZURE_DEEPSEEK_API_KEY"] = "ArSjteP5YKOUBTQRyB0fb1hXBgq2Sui96wZmoAou7eiHOdSPa0JHJQQJ99CFACYeBjFXJ3w3AAAAACOGxVOz"
os.environ["AZURE_DEEPSEEK_ENDPOINT"] = "https://arslan15114.services.ai.azure.com/openai/v1/chat/completions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("src.pipeline").setLevel(logging.INFO)

from src.pipeline.orchestrator import DigitizationOrchestrator
from src.pipeline.db_writer import DBWriter

def run_test():
    if len(sys.argv) < 2:
        print("Usage: python scratch_test_9grade.py <textbook_id>")
        sys.exit(1)
        
    textbook_id = sys.argv[1]
    
    writer = DBWriter()
    toc = writer.load_toc(textbook_id)
    if not toc:
        print("No TOC found!")
        sys.exit(1)
        
    paragraphs = [t for t in toc if t.get("page_start") is not None]
    if not paragraphs:
        print("No paragraphs with page_start in TOC!")
        sys.exit(1)
        
    target = paragraphs[0]
    print(f"Targeting paragraph: {target['title']} (page {target['page_start']} - number {target['number']})")
    
    orchestrator = DigitizationOrchestrator(
        job_id="test_job_123",
        textbook_id=textbook_id,
        class_level=9,
        content_first=False,
        target_paragraphs={str(target["number"])}
    )
    
    source_path = "/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf"
    print(f"Starting test run for paragraph number {target['number']}...")
    tasks_written = orchestrator.run_pdf(source_path)
    print(f"Test run completed. Tasks written: {tasks_written}")

if __name__ == "__main__":
    run_test()
