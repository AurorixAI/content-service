"""
Тест нового FigureExtractor для сканированного PDF учебника.

Запуск:
  docker exec content-worker python3 /app/scripts/test_scanned_figures.py
"""
import logging
import sys
import os

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Проверяем импорт
sys.path.insert(0, "/app")
os.environ.setdefault("APP_ENV", "production")

from src.pipeline.figures import FigureExtractor, figure_id_for

PDF_PATH = "/app/textbooks/9_grade/7fb9904d29_algebra_9_klass_ju_n_makarychev_2023_g_.pdf"
TEXTBOOK_ID = "5a9f7fea-1394-4141-9d58-015972e83acc"

# Тестируем на стр. 50–52 (там есть графики параболы Рис. 22)
TEST_PAGE_START = 50
TEST_PAGE_END = 52

def main():
    print("=" * 60)
    print("FigureExtractor Test — Scanned PDF")
    print("=" * 60)

    extractor = FigureExtractor(TEXTBOOK_ID)

    print(f"\n[1] Тестовое извлечение стр. {TEST_PAGE_START}–{TEST_PAGE_END}")
    try:
        figures = extractor.extract_pages(PDF_PATH, TEST_PAGE_START, TEST_PAGE_END)
    except Exception as e:
        print(f"  ОШИБКА extract_pages: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\n  Результат: {len(figures)} рисунков")
    for fig in figures:
        print(f"    - {fig.figure_id}: bbox={fig.bbox}, file={fig.file_path}")
        import os
        if os.path.exists(fig.file_path):
            size = os.path.getsize(fig.file_path)
            import struct
            # Читаем размер PNG
            with open(fig.file_path, "rb") as f:
                sig = f.read(8)
                if sig == b'\x89PNG\r\n\x1a\n':
                    f.seek(16)
                    w = struct.unpack('>I', f.read(4))[0]
                    h = struct.unpack('>I', f.read(4))[0]
                    print(f"      PNG: {w}x{h}px, {size//1024}KB ✅")
                else:
                    print(f"      Файл не PNG! ({size} bytes)")
        else:
            print(f"      ❌ Файл не найден!")

    if not figures:
        print("\n  [!] Рисунков не найдено. Проверяем Vision AI fallback через OCR...")
        print("      Вероятно нужен Vision endpoint корректный.")
        print("      Проверим что тест детекта PDF работает:")
        import fitz
        doc = fitz.open(PDF_PATH)
        is_scanned = extractor._detect_scanned_pdf(doc, fitz, TEST_PAGE_START, TEST_PAGE_END)
        print(f"      is_scanned={is_scanned}")
        doc.close()
    else:
        print(f"\n[2] Описание рисунков (describe_all)...")
        try:
            figures = extractor.describe_all(figures)
            for fig in figures:
                print(f"    {fig.figure_id}: is_useful={fig.is_useful}, reason={fig.usefulness_reason}")
                print(f"      alt_text: {fig.alt_text[:80] if fig.alt_text else '(пусто)'}")
        except Exception as e:
            print(f"  ОШИБКА describe_all: {e}")

    print("\n✅ Тест завершён")

if __name__ == "__main__":
    main()
