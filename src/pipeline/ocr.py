"""
ALGO V1 — OCR Module
src/pipeline/ocr.py

Бэкенд: GeminiVisionOCR — PDF → Markdown через Gemini Vision (Vertex AI, ADC auth).
Рендерит страницы в PNG (PyMuPDF) и отправляет батчами в Gemini.
Кэширует результат по SHA-256 хэшу PDF.
"""

import base64
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from src.core.config import get_settings
from src.pipeline.models import Figure
from src.pipeline.ocr_utils import is_usable_ocr_text

log = logging.getLogger(__name__)

# Prompt for page-level OCR extraction
_PAGE_PROMPT_BASE = """\
Ты — OCR-система для казахстанского математического учебника (русский язык).
Извлеки весь текст с этих страниц учебника точно и полностью.

ПРАВИЛА:
1. Весь математический текст — в LaTeX:
   - Inline формулы: $формула$
   - Display формулы (на отдельной строке): $$формула$$
2. Сохраняй структуру: заголовки (§, глава, параграф), нумерацию задач (1., 2., 3.*, №1 и т.д.)
3. Таблицы — в Markdown (| col | col |)
4. РИСУНКИ: вставляй маркер в поток текста там, где рисунок расположен:
   [FIGURE id="fig-pN-K"]
   где N — номер страницы, K — порядковый номер рисунка на странице (сверху вниз).
   Список валидных рисунков для этого батча дан ниже — используй ТОЛЬКО ИХ.
   Не выдумывай ID. Если на странице нет рисунков в списке — не вставляй [FIGURE].
5. Если страница пустая — пиши [Пустая страница]
6. НЕ добавляй объяснений, комментариев или вводных фраз — только текст учебника.

Отвечай текстом страниц подряд, разделяя страницы строкой: --- страница ---
"""


class GeminiVisionOCR:
    """PDF → Markdown через Gemini Vision (Vertex AI, ADC auth)."""

    BATCH_SIZE = 4
    RENDER_DPI = 150
    REQUEST_DELAY = 1.0

    def __init__(self):
        settings = get_settings()
        self.cache_dir = Path(settings.pipeline_cache_dir)
        self.cache_dir.mkdir(exist_ok=True)

    def process_pdf(
        self,
        pdf_path: str,
        figures_by_page: Optional[dict[int, list[Figure]]] = None,
    ) -> str:
        pdf = Path(pdf_path)
        if not pdf.exists():
            raise FileNotFoundError(f"PDF не найден: {pdf_path}")

        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"gemini_{file_hash}.md"

        if cache_file.exists():
            cached = cache_file.read_text(encoding="utf-8")
            if is_usable_ocr_text(cached):
                log.info("Gemini Vision OCR из кэша: %s", cache_file)
                return cached
            log.warning("Gemini Vision OCR: stale/empty cache removed %s", cache_file)
            cache_file.unlink(missing_ok=True)

        log.info(
            "Запуск Gemini Vision OCR: %s (%d KB)",
            pdf.name,
            pdf.stat().st_size // 1024,
        )
        text = self._ocr_with_gemini(pdf, figures_by_page or {})
        if is_usable_ocr_text(text):
            cache_file.write_text(text, encoding="utf-8")
        else:
            log.warning("Gemini Vision OCR: result not cached (too short or error)")
        log.info("Gemini Vision OCR завершён: %d символов", len(text))
        return text

    def _text_layer_fallback(self, doc, page_index: int) -> str:
        """Текстовый слой PDF, когда Vision не смог распознать страницу.

        Раньше на этом месте стояла пустая строка: страница просто исчезала из
        книги, и в логе оставалась одна строчка ERROR. На `textzadachi5` так
        терялась стр. 7 — плотная страница с задачами 4–8 и 18–21, при том что
        в PDF по ней лежал готовый текстовый слой на 1 747 символов.

        Слой есть не у всякой книги (чистый скан его не имеет), поэтому это
        именно фолбэк, а не замена OCR: у сканов с текстовым слоем он спасает
        страницу бесплатно, у остальных — вернёт пусто, как и раньше.
        """
        try:
            raw = doc[page_index].get_text() or ""
        except Exception as exc:  # noqa: BLE001
            log.error("Text-layer fallback failed p%d: %s", page_index + 1, exc)
            return ""
        if is_usable_ocr_text(raw):
            log.warning(
                "OCR failed p%d — подставлен текстовый слой PDF (%d симв.)",
                page_index + 1, len(raw.strip()),
            )
            return raw
        log.error("Single-page OCR failed: p%d (текстового слоя тоже нет)", page_index + 1)
        return ""

    def process_pages(
        self,
        pdf_path: str,
        page_start: int,
        page_end: int,
        figures_by_page: Optional[dict[int, list[Figure]]] = None,
        *,
        force_refresh: bool = False,
    ) -> str:
        """OCR диапазона [page_start, page_end] (1-based, inclusive)."""
        pdf = Path(pdf_path)
        if not pdf.exists():
            raise FileNotFoundError(f"PDF не найден: {pdf_path}")

        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"gemini_{file_hash}_p{page_start}-{page_end}.md"

        if not force_refresh and cache_file.exists():
            cached = cache_file.read_text(encoding="utf-8")
            if is_usable_ocr_text(cached):
                log.info(
                    "Gemini Vision OCR pages %d-%d из кэша",
                    page_start, page_end,
                )
                return cached
            log.warning(
                "OCR cache unusable for p%d-%d (%d chars) — re-OCR",
                page_start, page_end, len(cached),
            )
            cache_file.unlink(missing_ok=True)

        text = self._ocr_with_gemini(
            pdf, figures_by_page or {},
            page_start=page_start, page_end=page_end,
        )
        if is_usable_ocr_text(text):
            cache_file.write_text(text, encoding="utf-8")
        else:
            log.warning(
                "OCR p%d-%d not cached: %d chars (unusable)",
                page_start, page_end, len(text),
            )
        return text

    def invalidate_pages_cache(
        self, pdf_path: str, page_start: int, page_end: int,
    ) -> bool:
        """Remove cached OCR for a page range. Returns True if file existed."""
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"gemini_{file_hash}_p{page_start}-{page_end}.md"
        if cache_file.exists():
            cache_file.unlink()
            log.info("OCR cache invalidated: p%d-%d", page_start, page_end)
            return True
        return False

    def read_cached_page(self, pdf_path: str, page: int) -> Optional[str]:
        """Return cached OCR text for a single page, or None if missing/unusable."""
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"gemini_{file_hash}_p{page}-{page}.md"
        if not cache_file.exists():
            return None
        cached = cache_file.read_text(encoding="utf-8")
        return cached if is_usable_ocr_text(cached) else None

    def count_cached_pages(
        self, pdf_path: str, page_start: int, page_end: int,
    ) -> int:
        """How many pages in [page_start, page_end] have usable OCR cache."""
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)
        n = 0
        for page in range(page_start, page_end + 1):
            cache_file = self.cache_dir / f"gemini_{file_hash}_p{page}-{page}.md"
            if cache_file.exists():
                cached = cache_file.read_text(encoding="utf-8")
                if is_usable_ocr_text(cached):
                    n += 1
        return n

    def _ocr_with_gemini(
        self,
        pdf: Path,
        figures_by_page: dict[int, list[Figure]],
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
    ) -> str:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF не установлен. Добавьте pymupdf в requirements.txt"
            )

        from src.pipeline.gemini_client import call_gemini_vision, get_pro_model

        doc = fitz.open(str(pdf))
        total_pages = len(doc)
        lo = max(1, page_start or 1) - 1
        hi = min(total_pages, page_end or total_pages)
        log.info("Страниц в PDF: %d (обрабатываем %d-%d)", total_pages, lo + 1, hi)

        results: list[str] = []
        mat = fitz.Matrix(self.RENDER_DPI / 72, self.RENDER_DPI / 72)

        for batch_start in range(lo, hi, self.BATCH_SIZE):
            batch_end = min(batch_start + self.BATCH_SIZE, hi)
            page_nums = list(range(batch_start, batch_end))

            page_label = (
                f"{batch_start + 1}–{batch_end}"
                if len(page_nums) > 1
                else str(batch_start + 1)
            )
            log.info(
                "Gemini Vision: страницы %s/%d (батч %d стр.)",
                page_label, total_pages, len(page_nums),
            )

            batch_text = self._ocr_page_batch(
                doc, page_nums, figures_by_page, mat, get_pro_model, call_gemini_vision,
            )

            if not is_usable_ocr_text(batch_text) and len(page_nums) > 1:
                log.warning(
                    "Batch OCR p%s unusable — fallback to 1 page/request",
                    page_label,
                )
                for pn0 in page_nums:
                    single = self._ocr_page_batch(
                        doc, [pn0], figures_by_page, mat,
                        get_pro_model, call_gemini_vision,
                    )
                    if is_usable_ocr_text(single):
                        results.append(single)
                    else:
                        results.append(self._text_layer_fallback(doc, pn0))
            elif is_usable_ocr_text(batch_text):
                results.append(batch_text)
            else:
                recovered = [self._text_layer_fallback(doc, pn0) for pn0 in page_nums]
                if any(recovered):
                    results.extend(recovered)
                else:
                    log.error("OCR failed for pages %s", page_label)
                    results.append("")

            if batch_end < hi:
                time.sleep(self.REQUEST_DELAY)

        doc.close()
        return "\n\n".join(r for r in results if r)

    def _ocr_page_batch(
        self,
        doc,
        page_nums: list[int],
        figures_by_page: dict[int, list[Figure]],
        mat,
        get_pro_model,
        call_gemini_vision,
    ) -> str:
        import fitz  # PyMuPDF

        image_parts: list[dict] = []
        for page_num in page_nums:
            page = doc[page_num]
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            png_bytes = pix.tobytes("png")
            b64 = base64.b64encode(png_bytes).decode("ascii")
            image_parts.append({"mimeType": "image/png", "data": b64})

        prompt = self._build_prompt(page_nums, figures_by_page)
        try:
            return call_gemini_vision(
                prompt,
                image_parts,
                model=get_pro_model(),
                temperature=0.05,
                max_tokens=8192,
                timeout=120,
            )
        except Exception as exc:
            log.error(
                "Gemini Vision ошибка на страницах %s: %s",
                page_nums, exc,
            )
            return ""

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    @staticmethod
    def _build_prompt(
        page_nums: list[int],
        figures_by_page: dict[int, list[Figure]],
    ) -> str:
        lines: list[str] = []
        for pn0 in page_nums:
            pn = pn0 + 1
            figs = figures_by_page.get(pn, [])
            if figs:
                ids = ", ".join(f.figure_id for f in figs)
                lines.append(f"  страница {pn}: {ids}")
            else:
                lines.append(f"  страница {pn}: нет рисунков")
        figures_block = "\n".join(lines) if lines else "  нет данных"
        return (
            _PAGE_PROMPT_BASE
            + "\nДОСТУПНЫЕ figure_id для этого батча:\n"
            + figures_block
            + "\n\nИспользуй ТОЛЬКО эти ID, в том порядке в котором рисунки встречаются в тексте."
        )
