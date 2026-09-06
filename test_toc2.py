import sys, logging
logging.basicConfig(level=logging.INFO)
from src.pipeline.ocr import AzureMistralOCR
from src.pipeline.deepseek_client import call_deepseek, _robust_parse_json

ocr = AzureMistralOCR()
pdf = '/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf'
text = ocr.process_pages(pdf, 237, 256)

prompt = """Ты — эксперт по школьным учебникам математики. Это страницы PDF учебника.
Найди и извлеки ОГЛАВЛЕНИЕ (содержание) учебника в виде структурированного JSON.

ТРЕБОВАНИЯ К ВЫВОДУ:
Верни массив объектов:
[
  {
    "number": "1",
    "title": "...",
    "level": 1,
    "parent_number": "",
    "page_start": 5,
    "page_end": null,
    "sort_order": 1
  }
]
""" + "\n\nТекст учебника (OCR):\n---\n" + text[-80000:] + "\n---"

print("Sending request to DeepSeek...")
res = call_deepseek(prompt, system_prompt="Верни только JSON массив.", temperature=0.1)
print(res[:500])
parsed = _robust_parse_json(res)
if isinstance(parsed, dict):
    parsed = parsed.get("toc") or parsed.get("entries") or []
print("Extracted:", len(parsed), "entries")
