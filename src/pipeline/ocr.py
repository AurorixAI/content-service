"""
ALGO V2 — OCR Module
src/pipeline/ocr.py

Бэкенд: AzureMistralOCR — PDF → Markdown через специализированный Azure Mistral Document AI.
Отправляет PDF-страницы в Mistral, который нативно возвращает премиальный Markdown + LaTeX.

Smart Figure Injection: результат OCR обогащается маркерами [FIGURE id="fig-pN-K"],
совместимыми с нашим TaskExtractor, на основе заранее вырезанных фигур FigureExtractor'ом.

Кэширует результат по SHA-256 хэшу PDF.
"""

import base64
import hashlib
import logging
import re
import time
import requests
from pathlib import Path
from typing import Optional

from src.core.config import get_settings
from src.pipeline.models import Figure
from src.pipeline.ocr_utils import is_usable_ocr_text

log = logging.getLogger(__name__)

# Паттерны нативных плейсхолдеров Mistral OCR для картинок
# Mistral возвращает изображения в виде: ![img-N-M.jpeg](img-N-M.jpeg) или ![](img-N-M.png)
_MISTRAL_IMG_RE = re.compile(
    r'!\[(?:[^\]]*)\]\((?:img-[^)]+|[^)]*\.(?:png|jpg|jpeg|gif|webp))\)',
    re.IGNORECASE,
)


def _inject_figure_markers(text: str, page_nums: list[int], figures_by_page: dict[int, list[Figure]]) -> str:
    """
    Заменяет нативные плейсхолдеры Mistral (![...](img-...)) на наши
    канонические маркеры [FIGURE id="fig-pN-K"].

    Алгоритм:
    1. Находим все нативные плейсхолдеры картинок в тексте (слева направо = сверху вниз).
    2. Для каждой страницы батча берём фигуры в том же порядке (сверху вниз).
    3. Заменяем плейсхолдеры на маркеры по очереди.
    4. Если плейсхолдеров больше, чем известных фигур — оставляем комментарий [FIGURE unknown].
    """
    # Собираем все известные figure_id для страниц батча, в порядке страниц и idx
    ordered_ids: list[str] = []
    for pn in page_nums:
        real_page = pn + 1  # page_nums — 0-based, страницы — 1-based
        for fig in figures_by_page.get(real_page, []):
            ordered_ids.append(fig.figure_id)

    if not ordered_ids:
        # Нет известных фигур — убираем нативные плейсхолдеры, чтобы не мусорить текст
        return _MISTRAL_IMG_RE.sub("[FIGURE placeholder]", text)

    replacements: list[str] = []
    counter = [0]  # mutable int для lambda

    def replacer(m: re.Match) -> str:
        idx = counter[0]
        counter[0] += 1
        if idx < len(ordered_ids):
            fid = ordered_ids[idx]
            return f'[FIGURE id="{fid}"]'
        return "[FIGURE unknown]"

    return _MISTRAL_IMG_RE.sub(replacer, text)


class AzureMistralOCR:
    """PDF → Markdown через Azure Mistral Document AI OCR.

    Включает Smart Figure Injection: если передан figures_by_page,
    нативные плейсхолдеры Mistral заменяются на каноничные маркеры
    [FIGURE id="fig-pN-K"], которые TaskExtractor и figure_links ожидают.
    """

    BATCH_SIZE = 3       # Mistral OCR легко обрабатывает 3-5 страниц за раз, используем 3 для безопасного батчинга в экстракции
    REQUEST_DELAY = 1.0  # Пауза между батчами (rate-limit Azure)
    MAX_RETRIES = 3      # Число попыток при временных ошибках API

    def __init__(self):
        settings = get_settings()
        self.cache_dir = Path(settings.pipeline_cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.api_key = settings.azure_mistral_api_key.strip()
        self.endpoint = settings.azure_mistral_endpoint.strip()

        if not self.api_key or not self.endpoint:
            log.warning("AZURE_MISTRAL_API_KEY или ENDPOINT не заданы. OCR упадёт при вызове.")

    # ── Public API (совместим с legacy GeminiVisionOCR) ──────────────────────

    def process_pdf(
        self,
        pdf_path: str,
        figures_by_page: Optional[dict[int, list[Figure]]] = None,
    ) -> str:
        pdf = Path(pdf_path)
        if not pdf.exists():
            raise FileNotFoundError(f"PDF не найден: {pdf_path}")

        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"mistral_{file_hash}.md"

        if cache_file.exists():
            cached = cache_file.read_text(encoding="utf-8")
            if is_usable_ocr_text(cached):
                log.info("Mistral OCR из кэша: %s", cache_file)
                return cached
            log.warning("Mistral OCR: stale/empty cache removed %s", cache_file)
            cache_file.unlink(missing_ok=True)

        log.info("Запуск Mistral OCR: %s (%d KB)", pdf.name, pdf.stat().st_size // 1024)
        text = self._ocr_with_mistral(pdf, figures_by_page or {})
        if is_usable_ocr_text(text):
            cache_file.write_text(text, encoding="utf-8")
        else:
            log.warning("Mistral OCR: результат не кэширован (слишком короткий или ошибка)")
        return text

    def process_pages(
        self,
        pdf_path: str,
        page_start: int,
        page_end: int,
        figures_by_page: Optional[dict[int, list[Figure]]] = None,
        *,
        force_refresh: bool = False,
        ignore_back_matter: bool = False,
    ) -> str:
        """OCR диапазона [page_start, page_end] (1-based, inclusive)."""
        pdf = Path(pdf_path)
        if not pdf.exists():
            raise FileNotFoundError(f"PDF не найден: {pdf_path}")

        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"mistral_{file_hash}_p{page_start}-{page_end}.md"

        if not force_refresh and cache_file.exists():
            cached = cache_file.read_text(encoding="utf-8")
            if is_usable_ocr_text(cached):
                log.info("Mistral OCR pages %d-%d из кэша", page_start, page_end)
                return cached
            log.warning("OCR cache unusable for p%d-%d — re-OCR", page_start, page_end)
            cache_file.unlink(missing_ok=True)

        text = self._ocr_with_mistral(
            pdf, figures_by_page or {},
            page_start=page_start, page_end=page_end,
            ignore_back_matter=ignore_back_matter,
        )
        if is_usable_ocr_text(text):
            cache_file.write_text(text, encoding="utf-8")
        else:
            log.warning("OCR p%d-%d not cached: %d chars (unusable)", page_start, page_end, len(text))
        return text

    def invalidate_pages_cache(self, pdf_path: str, page_start: int, page_end: int) -> bool:
        """Remove cached OCR for a page range. Returns True if file existed."""
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"mistral_{file_hash}_p{page_start}-{page_end}.md"
        if cache_file.exists():
            cache_file.unlink()
            log.info("OCR cache invalidated: p%d-%d", page_start, page_end)
            return True
        return False

    def read_cached_page(self, pdf_path: str, page: int) -> Optional[str]:
        """Return cached OCR text for a single page, or None if missing/unusable."""
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)
        cache_file = self.cache_dir / f"mistral_{file_hash}_p{page}-{page}.md"
        if not cache_file.exists():
            return None
        cached = cache_file.read_text(encoding="utf-8")
        return cached if is_usable_ocr_text(cached) else None

    def count_cached_pages(self, pdf_path: str, page_start: int, page_end: int) -> int:
        """How many pages in [page_start, page_end] have usable OCR cache."""
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)
        n = 0
        for page in range(page_start, page_end + 1):
            cache_file = self.cache_dir / f"mistral_{file_hash}_p{page}-{page}.md"
            if cache_file.exists():
                cached = cache_file.read_text(encoding="utf-8")
                if is_usable_ocr_text(cached):
                    n += 1
        return n

    def detect_back_matter_start(
        self,
        pdf_path: str,
        scan_from: int,
        total_pages: int,
    ) -> int:
        """Определяет номер первой страницы с ответами/указателями (back-matter).

        Стратегия (без лишних API-вызовов):
        1. Ищем существующий большой кэш (mistral_{hash}_p{scan_from}-*.md)
           — такой файл появляется при первом прогоне пайплайна через весь §31.
        2. Если нашли — разбиваем по ``--- страница ---`` (батчи) и проверяем каждый.
        3. Если кэша нет — делаем OCR постранично (1 стр.), чтобы найти boundary.

        Возвращает:
            Номер (1-based) первой страницы back-matter,
            или ``total_pages + 1`` если back-matter не найден
            (т.е. весь диапазон — реальный контент).
        """
        pdf = Path(pdf_path)
        file_hash = self._hash_file(pdf)

        log.info(
            "detect_back_matter_start: scan from page %d / %d",
            scan_from, total_pages,
        )

        # ── Шаг 1: ищем подходящие файлы кэша ──────────────────────────────
        # Ищем файлы вида mistral_{hash}_p{scan_from}-{N}.md (большие батчи)
        cache_candidates: list[tuple[int, int, Path]] = []  # (batch_start, batch_end, path)
        prefix = f"mistral_{file_hash}_p"
        for f in self.cache_dir.glob(f"{prefix}*.md"):
            name = f.stem.replace(prefix, "")  # "178-256"
            parts = name.split("-")
            if len(parts) != 2:
                continue
            try:
                p_start, p_end = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            # Ищем файлы, начинающиеся с нашего диапазона или покрывающие его
            if p_start <= scan_from and p_end >= scan_from:
                cache_candidates.append((p_start, p_end, f))

        # Сортируем:
        # 1. По близости p_start к scan_from (по возрастанию)
        # 2. По p_end (по убыванию), чтобы отдавать приоритет наиболее полным кэшам
        cache_candidates.sort(key=lambda x: (abs(x[0] - scan_from), -x[1]))

        for batch_p_start, batch_p_end, cache_path in cache_candidates:
            cached = cache_path.read_text(encoding="utf-8")
            if not is_usable_ocr_text(cached):
                continue

            log.info(
                "detect_back_matter_start: using cache %s (p%d-%d)",
                cache_path.name, batch_p_start, batch_p_end,
            )

            # Разбиваем по разделителю батчей
            batches = cached.split("\n\n--- страница ---\n\n")
            # Каждый батч = BATCH_SIZE страниц (обычно 3).
            # Нумерация: батч i → страницы batch_p_start + i*BATCH_SIZE ... + BATCH_SIZE-1
            for i, batch_text in enumerate(batches):
                batch_page_start_1based = batch_p_start + i * self.BATCH_SIZE  # 1-based
                if batch_page_start_1based < scan_from:
                    continue  # пропускаем батчи до нашей точки начала

                # page_num 0-based для _is_back_matter_page
                page_num_0based = batch_page_start_1based - 1
                if self._is_back_matter_page(batch_text, page_num_0based, total_pages):
                    log.info(
                        "detect_back_matter_start: back-matter at page ~%d (batch %d of cache %s)",
                        batch_page_start_1based, i, cache_path.name,
                    )
                    return batch_page_start_1based  # 1-based: первая страница ответов

            # Если весь этот кэш-файл пройден и в нём не обнаружено ответов,
            # мы НЕ выходим из функции сразу, а продолжаем проверять другие файлы кэша (если есть).
            log.info(
                "detect_back_matter_start: no back-matter found inside cache range %s (p%d-%d)",
                cache_path.name, batch_p_start, batch_p_end,
            )


        # ── Шаг 2: кэша нет — сканируем постранично через OCR ──────────────
        log.info(
            "detect_back_matter_start: no cache found for p%d+, scanning page-by-page via OCR",
            scan_from,
        )
        for page in range(scan_from, total_pages + 1):
            try:
                text = self.process_pages(pdf_path, page, page, figures_by_page={})
            except Exception as exc:
                log.warning("detect_back_matter_start: OCR failed p%d: %s", page, exc)
                continue
            if self._is_back_matter_page(text, page - 1, total_pages):
                log.info(
                    "detect_back_matter_start: back-matter found at page %d (OCR scan)", page,
                )
                return page

        log.info("detect_back_matter_start: no back-matter found in p%d–%d", scan_from, total_pages)
        return total_pages + 1

    def _ocr_with_mistral(
        self,
        pdf: Path,
        figures_by_page: dict[int, list[Figure]],
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        ignore_back_matter: bool = False,
    ) -> str:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf))
        total_pages = len(doc)
        lo = max(1, page_start or 1) - 1  # 0-based
        hi = min(total_pages, page_end or total_pages)
        log.info("Страниц в PDF: %d (обрабатываем %d-%d)", total_pages, lo + 1, hi)

        results: list[str] = []
        stopped_by_back_matter = False

        for batch_start in range(lo, hi, self.BATCH_SIZE):
            if stopped_by_back_matter:
                break
            batch_end = min(batch_start + self.BATCH_SIZE, hi)
            page_nums = list(range(batch_start, batch_end))  # 0-based

            log.info(
                "Mistral OCR: страницы %d–%d (батч %d стр.)",
                batch_start + 1, batch_end, len(page_nums),
            )

            # Нарезаем нужные страницы в mini-PDF в памяти
            new_doc = fitz.open()
            for pn in page_nums:
                new_doc.insert_pdf(doc, from_page=pn, to_page=pn)
            pdf_bytes = new_doc.write()
            new_doc.close()

            # Отправляем в Mistral
            raw_json = self._call_azure_mistral_ocr_raw(pdf_bytes)
            page_texts: list[str] = []
            if raw_json and "pages" in raw_json:
                page_texts = [p.get("markdown", "") for p in raw_json["pages"]]
            else:
                flat_text = self._parse_mistral_response(raw_json)
                page_texts = [flat_text] if flat_text else []

            # Проверяем каждую страницу батча на back-matter
            for idx, text in enumerate(page_texts):
                if idx < len(page_nums):
                    real_page_num = page_nums[idx]  # 0-based
                    if not ignore_back_matter and self._is_back_matter_page(text, real_page_num, total_pages):
                        log.info(
                            "OCR: обнаружен раздел ответов/указателей на стр. %d. Прекращаем обработку.",
                            real_page_num + 1,
                        )
                        stopped_by_back_matter = True
                        # Добавляем страницы ДО страницы с ответами
                        if idx > 0:
                            partial_raw = "\n\n".join(page_texts[:idx])
                            enriched = _inject_figure_markers(partial_raw, page_nums[:idx], figures_by_page)
                            results.append(enriched)
                        break

            if stopped_by_back_matter:
                break

            # Если всё хорошо — обогащаем весь батч маркерами
            full_raw = "\n\n".join(page_texts)
            if is_usable_ocr_text(full_raw):
                enriched = _inject_figure_markers(full_raw, page_nums, figures_by_page)
                results.append(enriched)
            else:
                log.error("Mistral OCR: пустой результат для страниц %d–%d", batch_start + 1, batch_end)
                results.append("")

            if batch_end < hi:
                time.sleep(self.REQUEST_DELAY)

        doc.close()
        return "\n\n--- страница ---\n\n".join(r for r in results if r)

    def _is_back_matter_page(self, text: str, page_num: int, total_pages: int) -> bool:
        """Определяет, является ли страница разделом ответов/указателей (back-matter).

        Обрабатывает артефакты сканированных PDF:
        - ``^{}[] ОТВЕТЫ``  (Mistral OCR часто добавляет ^{}[])
        - «о т в е т ы»    (разреженный шрифт)
        - «ответы к главе»  / «ответы к упражнениям»
        """
        if page_num < 40:  # В начале учебника ответов не бывает (защита от ложного срабатывания)
            return False
        if page_num >= total_pages - 8:  # Последние 8 страниц — всегда back-matter
            return True

        low = text.strip().lower()
        chunk = low[:300]

        # Убираем OCR-артефакты сканированных книг: ^{}[], пробелы в словах
        clean = re.sub(r'\^\{\}\[\]\s*', '', chunk)  # убираем ^{}[]
        # Нормализуем пробелы для поиска (ловим «о т в е т ы» → «ответы»)
        norm = "".join(clean.split())

        back_markers = (
            "ответы",
            "предметныйуказатель",
            "содержание",           # если «Содержание» вынесено в отдельный раздел
            "указатель",
            "mundarija",            # узбекский учебник
            "литература",
            "ответыкглаве",
            "ответыкупражнениям",
            "ответыкзадачам",
        )
        for m in back_markers:
            if m in norm:
                log.debug(
                    "_is_back_matter_page: page %d matched marker '%s'", page_num + 1, m,
                )
                return True

        # Дополнительная проверка: высокая плотность КОРОТКИХ строк с ответами.
        # Раздел «Ответы»: «530. 125 м.», «531. а) 65; б) 230» — числа + КОРОТКИЙ ответ.
        # Реальные задачи тоже начинаются с числа (641. Периметр...) но они ДЛИННЫЕ (>60 символов).
        # Поэтому считаем ТОЛЬКО строки, которые:
        #   - начинаются с 3-значного и более числа (задачи в учебниках обычно 3-значные: 530, 641)
        #   - короче 65 символов (ответ, не условие)
        lines = [ln.strip() for ln in low.split("\n") if ln.strip()]
        if len(lines) >= 8:
            ans_patterns = 0
            for line in lines[:20]:
                if (
                    re.match(r'^\d{3,4}[\s\.]+', line)   # 3-4 цифры + разделитель
                    and len(line) <= 65                     # КОРОТКАЯ строка = ответ
                ):
                    ans_patterns += 1
            if ans_patterns >= 6:
                log.info(
                    "_is_back_matter_page: page %d — short-answer density %d/20 → back-matter",
                    page_num + 1, ans_patterns,
                )
                return True

        return False

    def _call_azure_mistral_ocr_raw(self, pdf_bytes: bytes) -> dict:
        """Отправляет PDF в Azure Mistral OCR и возвращает JSON-ответ."""
        b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": "mistral-document-ai-2512",
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64_pdf}",
            },
        }

        url = self.endpoint
        if "?" not in url:
            url += "?api-version=2024-04-01-preview"

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=180)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (429, 503):
                    wait = 15 * attempt
                    log.warning("Mistral OCR rate-limit (%s) — ожидание %ds", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                else:
                    log.error("Mistral OCR API Error %s: %s", resp.status_code, resp.text[:500])
                    return {}
            except requests.Timeout:
                log.warning("Mistral OCR: timeout (попытка %d/%d)", attempt, self.MAX_RETRIES)
            except Exception as exc:
                log.error("Mistral OCR: неожиданная ошибка: %s", exc)
                return {}
        return {}


    def _call_azure_mistral_ocr(self, pdf_bytes: bytes) -> str:
        """Отправляет PDF (base64) в Azure Mistral OCR, возвращает Markdown-текст."""
        b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": "mistral-document-ai-2512",
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{b64_pdf}",
            },
        }

        url = self.endpoint
        if "?" not in url:
            url += "?api-version=2024-04-01-preview"

        last_error: Exception = RuntimeError("No attempts made")
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=180)
                if resp.status_code == 200:
                    return self._parse_mistral_response(resp.json())
                elif resp.status_code in (429, 503):
                    wait = 15 * attempt
                    log.warning("Mistral OCR rate-limit (%s) — ожидание %ds", resp.status_code, wait)
                    time.sleep(wait)
                    last_error = RuntimeError(f"HTTP {resp.status_code}")
                    continue
                else:
                    log.error("Mistral OCR API Error %s: %s", resp.status_code, resp.text[:500])
                    return ""
            except requests.Timeout:
                log.warning("Mistral OCR: timeout (попытка %d/%d)", attempt, self.MAX_RETRIES)
                last_error = TimeoutError("Request timeout")
            except Exception as exc:
                log.error("Mistral OCR: неожиданная ошибка: %s", exc)
                return ""

        log.error("Mistral OCR: исчерпаны попытки: %s", last_error)
        return ""

    @staticmethod
    def _parse_mistral_response(result_json: dict) -> str:
        """Универсальная распаковка ответа Mistral OCR (формат может меняться в Azure)."""
        # Формат Mistral Document AI: {"pages": [{"markdown": "..."}]}
        if "pages" in result_json:
            return "\n\n".join(
                p.get("markdown", "") for p in result_json["pages"]
            )
        # Chat-compatible: {"choices": [{"message": {"content": "..."}}]}
        if "choices" in result_json:
            return result_json["choices"][0]["message"]["content"]
        # Flat: {"content": "..."}
        if "content" in result_json:
            return result_json["content"]
        # Flat: {"text": "..."}
        if "text" in result_json:
            return result_json["text"]
        log.warning("Mistral OCR: неизвестный формат ответа, keys=%s", list(result_json.keys()))
        return str(result_json)

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]


# Псевдоним для обратной совместимости (чтобы не сломать старые импорты в orchestrator)
GeminiVisionOCR = AzureMistralOCR
