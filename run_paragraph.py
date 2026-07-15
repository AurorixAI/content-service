"""
Запускает оцифровку одного параграфа 9 класса через боевой Orchestrator.
Использование: python run_paragraph.py <paragraph_number> [--force-clear]
Пример:        python run_paragraph.py 31 --force-clear
"""
import argparse
import hashlib
import sys
import logging
import os
from pathlib import Path

os.environ["AZURE_MISTRAL_API_KEY"] = "ArSjteP5YKOUBTQRyB0fb1hXBgq2Sui96wZmoAou7eiHOdSPa0JHJQQJ99CFACYeBjFXJ3w3AAAAACOGxVOz"
os.environ["AZURE_MISTRAL_ENDPOINT"] = "https://arslan15114.services.ai.azure.com/providers/mistral/azure/ocr"
os.environ["AZURE_DEEPSEEK_API_KEY"] = "ArSjteP5YKOUBTQRyB0fb1hXBgq2Sui96wZmoAou7eiHOdSPa0JHJQQJ99CFACYeBjFXJ3w3AAAAACOGxVOz"
os.environ["AZURE_DEEPSEEK_ENDPOINT"] = "https://arslan15114.services.ai.azure.com/openai/v1/chat/completions"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("src.pipeline").setLevel(logging.INFO)
logging.getLogger("pipeline").setLevel(logging.INFO)

TEXTBOOK_ID  = "5a9f7fea-1394-4141-9d58-015972e83acc"
PDF_PATH     = "/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf"
CLASS_LEVEL  = 9
JOB_ID       = "para_run_9g"

from src.pipeline.db_writer import DBWriter
from src.pipeline.orchestrator import DigitizationOrchestrator
from src.core.config import get_settings
from sqlalchemy import create_engine, text


def _pdf_hash(pdf_path: str) -> str:
    return hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]


def _clear_paragraph_data(toc_id: int, pdf_path: str, page_start: int, page_end: int) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    removed = 0

    cache_file = Path(settings.pipeline_cache_dir) / f"gemini_{_pdf_hash(pdf_path)}_p{page_start}-{page_end}.md"
    if cache_file.exists():
        cache_file.unlink()
        print(f"[OK] cleared OCR cache: {cache_file}")

    with engine.begin() as conn:
        task_ids = [r[0] for r in conn.execute(
            text("SELECT id FROM tasks_master WHERE toc_id = :toc_id"),
            {"toc_id": toc_id},
        ).fetchall()]
        if task_ids:
            conn.execute(text("DELETE FROM textbook_tasks WHERE task_id = ANY(:ids)"), {"ids": task_ids})
            conn.execute(text("DELETE FROM tasks_master WHERE id = ANY(:ids)"), {"ids": task_ids})
            removed = len(task_ids)

    return removed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paragraph_number", nargs="?", default="1")
    ap.add_argument("--force-clear", action="store_true", help="Delete existing paragraph tasks and OCR cache before rerun")
    args = ap.parse_args()

    para_num = args.paragraph_number

    # Загружаем TOC, находим параграф
    writer = DBWriter()
    toc = writer.load_toc(TEXTBOOK_ID)
    para = next((t for t in toc if str(t.get("number","")) == para_num), None)

    if not para:
        print(f"[ERROR] Параграф §{para_num} не найден в TOC")
        print("Доступные параграфы:")
        for t in toc:
            print(f"  §{t['number']} — {t['title'][:60]}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  ОЦИФРОВКА §{para['number']} — {para['title']}")
    print(f"  Страницы: {para.get('page_start')}–{para.get('page_end')}")
    print(f"  toc_id:   {para['id']}")
    print(f"{'='*60}\n")

    if args.force_clear:
        removed = _clear_paragraph_data(int(para["id"]), PDF_PATH, int(para["page_start"]), int(para["page_end"]))
        print(f"[OK] cleared existing paragraph data: {removed} task(s)")

    orchestrator = DigitizationOrchestrator(
        job_id=JOB_ID,
        textbook_id=TEXTBOOK_ID,
        class_level=CLASS_LEVEL,
        content_first=False,
        target_paragraphs={para_num},
    )

    written = orchestrator.run_pdf(PDF_PATH)
    print(f"\n{'='*60}")
    print(f"  §{para['number']} завершен. Записано задач: {written}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
