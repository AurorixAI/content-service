"""Content Service — Figures Extractor & Describer

PDF → отдельные PNG-вырезки каждого рисунка + структурное описание
через Azure Mistral OCR (alt_text + semantic_json для AI-компонентов).

Полученные ID (fig-p{page}-{idx}) каноничны: тот же набор передаётся в OCR-промпт,
поэтому Mistral может вставлять маркеры [FIGURE id="fig-p12-1"] в нужных местах,
а task_extractor — извлекать их в task.figure_refs.

Кэш:
  {pipeline_cache_dir}/figures/{textbook_id}/{figure_id}.png   — вырезка
  {pipeline_cache_dir}/figures/{textbook_id}/{figure_id}.json  — описание

Режимы экстракции:
  EMBEDDED — стандартный: bbox из page.get_image_info() (для цифровых PDF).
  SCANNED  — для сканированных фото-PDF:
             1. Рендерит страницу в 300 DPI PNG.
             2. Отправляет PNG в Mistral OCR → получает pages[].images[] с
                пиксельными bbox (top_left_x/y, bottom_right_x/y) и dimensions.
             3. Нормализует пиксели → pt-координаты PDF страницы.
             4. Прецизионный кроп каждого bbox с паддингом 18pt при 300 DPI.
             5. Сохраняет PNG высокого качества.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import List, Optional

import requests

from src.core.config import get_settings
from src.pipeline.models import Figure

log = logging.getLogger(__name__)


# ── Константы качества ─────────────────────────────────────────────────────────

# DPI для рендеринга всей страницы (вход в Mistral OCR)
_PAGE_RENDER_DPI = 300

# DPI для финального кропа-вырезки (выходной PNG рисунка)
_FIGURE_CROP_DPI = 300

# DPI для стандартного embedded-режима
_EMBEDDED_FIGURE_DPI = 200

# Минимальный размер рисунка в пунктах PDF (ширина или высота)
_MIN_FIGURE_PT = 40

# Расширяем bbox на N пунктов (захватываем подписи «Рис. N»)
_BBOX_PADDING_PT = 18

# Порог: если embedded-image занимает >65% страницы → PDF сканированный
_SCANNED_PAGE_COVERAGE_THRESHOLD = 0.65

# Минимальная площадь рисунка в долях страницы (отбрасываем микро-артефакты)
_MIN_FIGURE_PAGE_FRACTION = 0.02  # 2% от страницы

# Максимум попыток при ошибке API
_API_MAX_RETRIES = 3

# Задержка между запросами (rate-limiting)
_API_REQUEST_DELAY = 1.0


# ── Промпт для описания рисунка ───────────────────────────────────────────────

_DESCRIBE_PROMPT = """\
Ты — эксперт-математик. Это рисунок из школьного учебника математики (русский язык).
Опиши его строго в формате JSON:

{
  "is_useful": true,
  "usefulness_reason": "",
  "alt_text": "",
  "type": "",
  "structure": {},
  "labels": [],
  "key_values": {}
}

usefulness_reason — одно из: math_diagram | function_plot | coordinate_grid |
  data_table | chart | photo | portrait | decorative | cover | ornament | other

is_useful=true: math_diagram, function_plot, coordinate_grid, data_table, chart
is_useful=false: photo, portrait, decorative, cover, ornament, other

Только JSON, без markdown. alt_text по-русски, кратко.
"""


def figure_id_for(textbook_id: str, page: int, idx: int) -> str:
    """Return a globally unique, stable figure ID.

    Page numbers repeat across textbooks, so ``fig-p30-1`` cannot safely be a
    primary key.  The short textbook UUID keeps IDs readable while making
    references unambiguous across the whole content bank.
    """
    return f"fig-{textbook_id[:8]}-p{page}-{idx}"


class FigureExtractor:
    """Вырезает рисунки из PDF и описывает их через Azure Mistral Document AI.

    Авто-детект:
    - EMBEDDED (цифровой PDF) → bbox из page.get_image_info()
    - SCANNED (фото-PDF) → Mistral OCR на rendered PNG → pages[].images[].bbox → кроп
    """

    def __init__(self, textbook_id: str):
        self.textbook_id = textbook_id
        settings = get_settings()
        self.figures_dir = Path(settings.figures_dir) / textbook_id
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = Path(settings.pipeline_cache_dir) / "figures" / textbook_id
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.url_prefix = settings.figures_url_prefix.rstrip("/")

        self._api_key = settings.azure_mistral_api_key.strip()
        self._endpoint = settings.azure_mistral_endpoint.strip()
        # Финальный OCR URL с api-version
        base = self._endpoint.split("?")[0]
        self._ocr_url = base + "?api-version=2024-04-01-preview"

    # ── Public API ─────────────────────────────────────────────────────────────

    def extract_all(self, pdf_path: str) -> List[Figure]:
        """Извлекает все рисунки из PDF. Описания добавляет describe_all()."""
        return self.extract_pages(pdf_path)

    def extract_pages(
        self,
        pdf_path: str,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
    ) -> List[Figure]:
        """Извлекает рисунки из диапазона [page_start, page_end] (1-based, inclusive).

        Авто-детект режима: EMBEDDED или SCANNED.
        """
        try:
            import fitz
        except ImportError as e:
            raise RuntimeError("PyMuPDF not installed (pip install pymupdf)") from e

        doc = fitz.open(pdf_path)
        total = len(doc)
        lo = max(1, page_start or 1)
        hi = min(total, page_end or total)

        is_scanned = self._detect_scanned_pdf(doc, fitz, lo, hi)
        mode = "SCANNED" if is_scanned else "EMBEDDED"
        log.info("FigureExtractor: %s mode=%s pages=%d–%d", pdf_path, mode, lo, hi)

        all_figures: List[Figure] = []
        for page_idx in range(lo - 1, hi):
            page = doc[page_idx]
            page_no = page_idx + 1
            if is_scanned:
                figs = self._extract_page_scanned(page, page_no, fitz)
            else:
                figs = self._extract_page_embedded(page, page_no, fitz)
            all_figures.extend(figs)
            # Небольшая пауза между страницами в SCANNED-режиме
            if is_scanned and page_no < hi:
                time.sleep(_API_REQUEST_DELAY)

        doc.close()
        log.info(
            "FigureExtractor: extracted %d figures (mode=%s pages=%d–%d)",
            len(all_figures), mode, lo, hi,
        )
        return all_figures

    def describe_all(self, figures: List[Figure]) -> List[Figure]:
        """Заполняет alt_text + semantic_json + is_useful через Mistral OCR.

        Кэширует по figure_id — повторный запуск бесплатен.
        """
        for fig in figures:
            cache_file = self.cache_dir / f"{fig.figure_id}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text(encoding="utf-8"))
                    fig.alt_text = data.get("alt_text", "")
                    fig.semantic_json = data
                    fig.is_useful = bool(data.get("is_useful", True))
                    fig.usefulness_reason = str(data.get("usefulness_reason", "")).strip()
                    continue
                except Exception:
                    pass

            try:
                png_bytes = Path(fig.file_path).read_bytes()
            except FileNotFoundError:
                log.warning("Figure file missing: %s", fig.figure_id)
                continue

            data = self._describe_figure(fig.figure_id, png_bytes)
            fig.alt_text = data.get("alt_text", "")
            fig.semantic_json = data
            fig.is_useful = bool(data.get("is_useful", True))
            fig.usefulness_reason = str(
                data.get("usefulness_reason", "describe_failed" if not data else "")
            ).strip()
            if data:
                cache_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        return figures

    def prune_unuseful(self, figures: List[Figure]) -> tuple[List[Figure], List[Figure]]:
        """Разделяет (полезные, отброшенные). У отброшенных удаляет PNG с диска."""
        kept, dropped = [], []
        for fig in figures:
            if fig.is_useful:
                kept.append(fig)
            else:
                dropped.append(fig)
                Path(fig.file_path).unlink(missing_ok=True)
        if dropped:
            reasons: dict[str, int] = {}
            for f in dropped:
                k = f.usefulness_reason or "unknown"
                reasons[k] = reasons.get(k, 0) + 1
            log.info("FigureExtractor: dropped %d unuseful → %s", len(dropped), reasons)
        return kept, dropped

    # ── PDF Type Detection ─────────────────────────────────────────────────────

    def _detect_scanned_pdf(self, doc, fitz, lo: int, hi: int) -> bool:
        """True если PDF сканированный (≥60% проверяемых страниц = full-page растр >65%)."""
        check_pages = list(range(lo - 1, min(lo + 4, hi)))
        scanned = 0
        for page_idx in check_pages:
            page = doc[page_idx]
            infos = page.get_image_info(xrefs=False)
            area = page.rect.width * page.rect.height
            if not infos or area == 0:
                continue
            for info in infos:
                bbox = info.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = bbox
                if (x1 - x0) * (y1 - y0) / area > _SCANNED_PAGE_COVERAGE_THRESHOLD:
                    scanned += 1
                    break
        ratio = scanned / max(1, len(check_pages))
        log.debug("Scan detect: %d/%d full-page (ratio=%.2f)", scanned, len(check_pages), ratio)
        return ratio >= 0.6

    # ── SCANNED Extraction — Mistral OCR + pages[].images[] ───────────────────

    def _extract_page_scanned(self, page, page_no: int, fitz) -> List[Figure]:
        """Рендерит страницу в PNG → Mistral OCR → кропит каждый img bbox."""

        # Шаг 1: Рендер 300 DPI → PNG bytes
        mat_render = fitz.Matrix(_PAGE_RENDER_DPI / 72, _PAGE_RENDER_DPI / 72)
        try:
            pix_full = page.get_pixmap(matrix=mat_render, colorspace=fitz.csRGB, alpha=False)
        except Exception as exc:
            log.warning("Render failed page %d: %s", page_no, exc)
            return []

        page_w_pt = page.rect.width
        page_h_pt = page.rect.height

        # Шаг 2: Mistral OCR → images[] (с кэшем по странице)
        vision_cache = self.cache_dir / f"vision_bbox_p{page_no}.json"
        detected: Optional[list] = None

        if vision_cache.exists():
            try:
                cached = json.loads(vision_cache.read_text(encoding="utf-8"))
                detected = cached.get("images", [])
                log.debug("Vision cache page %d → %d images", page_no, len(detected))
            except Exception:
                detected = None

        if detected is None:
            png_bytes = pix_full.tobytes("png")
            detected, ocr_dims = self._mistral_ocr_images(png_bytes, page_no)
            try:
                vision_cache.write_text(
                    json.dumps({"images": detected, "dims": ocr_dims}, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
        else:
            # Восстанавливаем dims из кэша
            try:
                cached = json.loads(vision_cache.read_text(encoding="utf-8"))
                ocr_dims = cached.get("dims", {})
            except Exception:
                ocr_dims = {}

        if not detected:
            log.debug("Page %d: no images found by Mistral OCR", page_no)
            return []

        # Шаг 3: Кроп каждого img bbox при 300 DPI
        # OCR dimensions: пикселей при каком DPI отрабатывал Mistral
        ocr_w_px = ocr_dims.get("width", pix_full.width)
        ocr_h_px = ocr_dims.get("height", pix_full.height)

        mat_crop = fitz.Matrix(_FIGURE_CROP_DPI / 72, _FIGURE_CROP_DPI / 72)
        figures: List[Figure] = []

        for idx, img_info in enumerate(detected, start=1):
            # Поля Mistral OCR: top_left_x, top_left_y, bottom_right_x, bottom_right_y (в пикселях OCR)
            tlx = img_info.get("top_left_x")
            tly = img_info.get("top_left_y")
            brx = img_info.get("bottom_right_x")
            bry = img_info.get("bottom_right_y")

            if any(v is None for v in [tlx, tly, brx, bry]):
                log.warning("Page %d img %d: missing bbox fields: %s", page_no, idx, img_info)
                continue

            tlx, tly, brx, bry = float(tlx), float(tly), float(brx), float(bry)

            # Нормализуем пиксели OCR → доли страницы
            if ocr_w_px <= 0 or ocr_h_px <= 0:
                log.warning("Page %d: invalid OCR dims %sx%s", page_no, ocr_w_px, ocr_h_px)
                continue

            x0_frac = tlx / ocr_w_px
            y0_frac = tly / ocr_h_px
            x1_frac = brx / ocr_w_px
            y1_frac = bry / ocr_h_px

            # Зажимаем в [0, 1]
            x0_frac = max(0.0, min(1.0, x0_frac))
            y0_frac = max(0.0, min(1.0, y0_frac))
            x1_frac = max(0.0, min(1.0, x1_frac))
            y1_frac = max(0.0, min(1.0, y1_frac))

            if x1_frac <= x0_frac or y1_frac <= y0_frac:
                continue

            # Минимальный размер: 2% площади страницы
            if (x1_frac - x0_frac) * (y1_frac - y0_frac) < _MIN_FIGURE_PAGE_FRACTION:
                log.debug(
                    "Page %d img %d: too small (%.1f%% x %.1f%%)",
                    page_no, idx,
                    (x1_frac - x0_frac) * 100, (y1_frac - y0_frac) * 100,
                )
                continue

            # Доли → pt-координаты PDF-страницы
            x0_pt = x0_frac * page_w_pt
            y0_pt = y0_frac * page_h_pt
            x1_pt = x1_frac * page_w_pt
            y1_pt = y1_frac * page_h_pt

            # Паддинг 18pt (захватываем «Рис. N»)
            clip = fitz.Rect(
                max(0.0, x0_pt - _BBOX_PADDING_PT),
                max(0.0, y0_pt - _BBOX_PADDING_PT),
                min(page_w_pt, x1_pt + _BBOX_PADDING_PT),
                min(page_h_pt, y1_pt + _BBOX_PADDING_PT),
            )

            # Кроп при 300 DPI
            try:
                pix_crop = page.get_pixmap(
                    matrix=mat_crop, clip=clip, colorspace=fitz.csRGB, alpha=False
                )
            except Exception as exc:
                log.warning("Crop failed page=%d idx=%d: %s", page_no, idx, exc)
                continue

            fid = figure_id_for(self.textbook_id, page_no, idx)
            file_path = self.figures_dir / f"{fid}.png"
            try:
                pix_crop.save(str(file_path))
            except Exception as exc:
                log.warning("Save failed %s: %s", file_path, exc)
                continue

            log.info(
                "Page %d: saved %s — %dx%d px (%.0f%%×%.0f%% of page)",
                page_no, fid, pix_crop.width, pix_crop.height,
                (x1_frac - x0_frac) * 100, (y1_frac - y0_frac) * 100,
            )

            figures.append(Figure(
                figure_id=fid,
                textbook_id=self.textbook_id,
                page=page_no,
                bbox=[round(x0_pt, 2), round(y0_pt, 2), round(x1_pt, 2), round(y1_pt, 2)],
                image_url=f"{self.url_prefix}/{self.textbook_id}/{fid}.png",
                file_path=str(file_path),
            ))

        log.info("Page %d SCANNED: %d/%d figures extracted", page_no, len(figures), len(detected))
        return figures

    def _mistral_ocr_images(
        self, png_bytes: bytes, page_no: int
    ) -> tuple[list[dict], dict]:
        """Отправляет PNG в Mistral OCR, возвращает (images_list, dimensions_dict).

        images_list: список dict с top_left_x/y, bottom_right_x/y (пиксели при dims DPI).
        dimensions_dict: {"width": px, "height": px, "dpi": N} — системные размеры ответа.
        """
        b64 = base64.b64encode(png_bytes).decode("ascii")
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}
        payload = {
            "model": "mistral-document-ai-2512",
            "document": {
                "type": "document_url",
                "document_url": f"data:image/png;base64,{b64}",
            },
            "include_image_base64": False,
        }

        for attempt in range(1, _API_MAX_RETRIES + 1):
            try:
                resp = requests.post(
                    self._ocr_url, headers=headers, json=payload, timeout=120
                )
                if resp.status_code == 200:
                    rj = resp.json()
                    pages = rj.get("pages", [])
                    if not pages:
                        log.warning("Mistral OCR page %d: empty pages[]", page_no)
                        return [], {}
                    page_data = pages[0]
                    images = page_data.get("images", [])
                    dims = page_data.get("dimensions", {})
                    log.info(
                        "Mistral OCR page %d: %d images, dims=%s (attempt %d)",
                        page_no, len(images), dims, attempt,
                    )
                    return images, dims

                elif resp.status_code in (429, 503):
                    wait = 15 * attempt
                    log.warning("Mistral OCR rate-limit %d page %d — wait %ds", resp.status_code, page_no, wait)
                    time.sleep(wait)
                else:
                    log.error(
                        "Mistral OCR HTTP %d page %d: %s",
                        resp.status_code, page_no, resp.text[:200],
                    )
                    return [], {}

            except requests.Timeout:
                log.warning("Mistral OCR timeout page %d (attempt %d/%d)", page_no, attempt, _API_MAX_RETRIES)
                if attempt == _API_MAX_RETRIES:
                    return [], {}
                time.sleep(10 * attempt)
            except Exception as exc:
                log.error("Mistral OCR error page %d: %s", page_no, exc)
                return [], {}

            if attempt < _API_MAX_RETRIES:
                time.sleep(2 ** attempt)

        return [], {}

    # ── EMBEDDED Extraction (цифровой PDF) ────────────────────────────────────

    def _extract_page_embedded(self, page, page_no: int, fitz) -> List[Figure]:
        """Стандартный режим для цифровых PDF: bbox из page.get_image_info()."""
        infos = page.get_image_info(xrefs=False)
        if not infos:
            return []

        page_area = page.rect.width * page.rect.height
        good: list[tuple[float, float, float, float]] = []
        for info in infos:
            bbox = info.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x0, y0, x1, y1 = bbox
            w_pt, h_pt = x1 - x0, y1 - y0
            if w_pt < _MIN_FIGURE_PT or h_pt < _MIN_FIGURE_PT:
                continue
            # Отбрасываем full-page изображения
            if page_area > 0 and (w_pt * h_pt) / page_area > _SCANNED_PAGE_COVERAGE_THRESHOLD:
                continue
            good.append((x0, y0, x1, y1))

        if not good:
            return []

        unique = sorted(set(good), key=lambda b: (round(b[1], 1), round(b[0], 1)))
        page_w, page_h = page.rect.width, page.rect.height
        mat = fitz.Matrix(_EMBEDDED_FIGURE_DPI / 72, _EMBEDDED_FIGURE_DPI / 72)

        figures: List[Figure] = []
        for idx, (x0, y0, x1, y1) in enumerate(unique, start=1):
            clip = fitz.Rect(
                max(0.0, x0 - _BBOX_PADDING_PT),
                max(0.0, y0 - _BBOX_PADDING_PT),
                min(page_w, x1 + _BBOX_PADDING_PT),
                min(page_h, y1 + _BBOX_PADDING_PT),
            )
            try:
                pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB, alpha=False)
            except Exception as exc:
                log.warning("Pixmap failed page %d: %s", page_no, exc)
                continue

            fid = figure_id_for(self.textbook_id, page_no, idx)
            file_path = self.figures_dir / f"{fid}.png"
            pix.save(str(file_path))
            figures.append(Figure(
                figure_id=fid,
                textbook_id=self.textbook_id,
                page=page_no,
                bbox=[round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                image_url=f"{self.url_prefix}/{self.textbook_id}/{fid}.png",
                file_path=str(file_path),
            ))
        return figures

    # ── Describe figure via Mistral OCR ───────────────────────────────────────

    def _describe_figure(self, figure_id: str, png_bytes: bytes) -> dict:
        """Описывает вырезанный рисунок через Mistral OCR (is_useful, alt_text, structure)."""
        b64 = base64.b64encode(png_bytes).decode("ascii")
        headers = {"api-key": self._api_key, "Content-Type": "application/json"}
        payload = {
            "model": "mistral-document-ai-2512",
            "document": {
                "type": "document_url",
                "document_url": f"data:image/png;base64,{b64}",
            },
        }
        try:
            resp = requests.post(self._ocr_url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                rj = resp.json()
                raw = ""
                if "pages" in rj:
                    raw = "\n".join(p.get("markdown", "") for p in rj["pages"])
                elif "choices" in rj:
                    raw = rj["choices"][0]["message"]["content"]
                elif "content" in rj:
                    raw = rj["content"]
                return _safe_json(raw)
            log.warning("Describe HTTP %d for %s", resp.status_code, figure_id)
        except Exception as exc:
            log.warning("Describe error %s: %s", figure_id, exc)
        return {}


# ── Helpers ────────────────────────────────────────────────────────────────────


def _safe_json(text: str) -> dict:
    """Парсит JSON, терпя markdown-обёртку и мусорный префикс."""
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                if isinstance(data, dict):
                    return data
                if isinstance(data, list):
                    return {"figures": data}
            except Exception:
                pass
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def figures_index_by_page(figures: List[Figure]) -> dict[int, List[Figure]]:
    """Группирует фигуры по странице для OCR-промпта."""
    idx: dict[int, List[Figure]] = {}
    for f in figures:
        idx.setdefault(f.page, []).append(f)
    return idx
