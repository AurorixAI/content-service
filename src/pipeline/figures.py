"""Content Service — Figures Extractor & Describer

PDF → отдельные PNG-вырезки каждого рисунка + структурное описание
через Gemini Vision (alt_text + semantic_json для AI-компонентов).

Полученные ID (fig-p{page}-{idx}) каноничны: тот же набор передаётся в OCR-промпт,
поэтому Gemini может вставлять ссылки [FIGURE id="fig-p12-1"] в нужных местах,
а task_extractor — извлекать их в task.figure_refs.

Кэш:
  {pipeline_cache_dir}/figures/{textbook_id}/{figure_id}.png   — вырезка
  {pipeline_cache_dir}/figures/{textbook_id}/{figure_id}.json  — описание
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import List, Optional

from src.core.config import get_settings
from src.pipeline.models import Figure

log = logging.getLogger(__name__)


# DPI для рендеринга bbox в PNG (выше — резче, тяжелее)
_FIGURE_DPI = 200

# Минимальный размер картинки (px) — отбрасываем мелкие иконки/буллеты
_MIN_FIGURE_PX = 80

# Расширяем bbox на N точек (подпись/нумерация рисунка)
_BBOX_PADDING_PT = 12

# Промпт для семантического описания рисунка
_DESCRIBE_PROMPT = """\
Ты — эксперт-математик. Это рисунок из школьного учебника математики (русский язык).
Опиши его строго в формате JSON:

{
  "is_useful": true,         // true если рисунок несёт мат. информацию для решения задачи
  "usefulness_reason": "",   // одно из: math_diagram | function_plot | coordinate_grid |
                              //         data_table | chart | photo | portrait | decorative |
                              //         cover | ornament | other
  "alt_text": "",            // короткое описание для screen-reader (1–2 предложения)
  "type": "",                // дублирует usefulness_reason (для удобства AI)
  "structure": {},           // ключевые элементы рисунка в машиночитаемом виде, напр.:
     // треугольник: {"shape":"triangle","vertices":["A","B","C"],"angles":{"C":90},"sides":{"AB":5}}
     // график:     {"function":"y=x^2-4","domain":[-3,3],"marked_points":[[2,0],[-2,0]]}
     // диаграмма:   {"items":[{"label":"...","value":...}]}
  "labels": [],              // подписи на рисунке
  "key_values": {}           // числовые данные (длины, углы, координаты)
}

КАК ОПРЕДЕЛИТЬ is_useful:
  TRUE  — рисунок можно использовать для решения задачи:
     • math_diagram      — геометрический чертёж (треугольник, окружность, углы)
     • function_plot     — график функции
     • coordinate_grid   — координатная плоскость с точками
     • data_table        — таблица с числами
     • chart             — диаграмма/гистограмма с данными
  FALSE — рисунок НЕ несёт мат. информации:
     • photo             — фото (дети, предметы, животные, бытовые сцены)
     • portrait          — портрет учёного/исторического лица
     • decorative        — декоративная иллюстрация, маскот, персонаж
     • cover             — обложка главы/раздела
     • ornament          — орнамент/рамка/иконка
     • other             — нечитаемый/непонятный фрагмент

ПРАВИЛА:
- Только JSON, без markdown-обёртки и комментариев.
- Если is_useful=false — structure/labels/key_values можно оставить пустыми.
- alt_text по-русски, кратко.
"""


def figure_id_for(page: int, idx: int) -> str:
    """Каноничный ID: fig-p{page}-{idx}, 1-based."""
    return f"fig-p{page}-{idx}"


class FigureExtractor:
    """Вырезает рисунки из PDF и описывает их Gemini Vision'ом."""

    def __init__(self, textbook_id: str):
        self.textbook_id = textbook_id
        settings = get_settings()
        # Постоянное хранилище для frontend
        self.figures_dir = Path(settings.figures_dir) / textbook_id
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        # Кэш описаний рядом с pipeline cache (переживает рестарт worker'а)
        self.cache_dir = Path(settings.pipeline_cache_dir) / "figures" / textbook_id
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.url_prefix = settings.figures_url_prefix.rstrip("/")

    # ── Public API ────────────────────────────────────────────────────────

    def extract_all(self, pdf_path: str) -> List[Figure]:
        """Извлекает все картинки из PDF и сохраняет PNG в figures_dir.

        Возвращает список Figure без описаний (alt_text/semantic_json пустые).
        Описания добавляет describe_all() — отдельным шагом.
        """
        return self.extract_pages(pdf_path)

    def extract_pages(
        self,
        pdf_path: str,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
    ) -> List[Figure]:
        """Извлекает рисунки только из диапазона страниц [page_start, page_end] (1-based, inclusive).

        Если границы не заданы — обрабатывает весь PDF (поведение extract_all).
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as e:
            raise RuntimeError("PyMuPDF not installed (pip install pymupdf)") from e

        doc = fitz.open(pdf_path)
        total = len(doc)
        lo = max(1, page_start or 1)
        hi = min(total, page_end or total)
        all_figures: List[Figure] = []
        for page_idx in range(lo - 1, hi):
            page = doc[page_idx]
            page_no = page_idx + 1
            figs = self._extract_page(page, page_no, fitz)
            all_figures.extend(figs)
        doc.close()
        log.info(
            "FigureExtractor: extracted %d figures from %s pages %d-%d",
            len(all_figures), pdf_path, lo, hi,
        )
        return all_figures

    def describe_all(self, figures: List[Figure]) -> List[Figure]:
        """Заполняет alt_text + semantic_json + is_useful для каждого рисунка через Gemini Vision.

        Описания кэшируются по figure_id; повторный запуск ничего не платит.
        Отбраковку по is_useful выполняет prune_unuseful() — отдельным шагом.
        """
        from src.pipeline.gemini_client import QuotaExhaustedError, call_gemini_vision, get_pro_model

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
                log.warning("Figure file missing for %s", fig.figure_id)
                continue

            b64 = base64.b64encode(png_bytes).decode("ascii")
            try:
                raw = call_gemini_vision(
                    _DESCRIBE_PROMPT,
                    [{"mimeType": "image/png", "data": b64}],
                    model=get_pro_model(),
                    temperature=0.1,
                    max_tokens=1024,
                    timeout=180,
                )
                data = _safe_json(raw)
                fig.alt_text = data.get("alt_text", "")
                fig.semantic_json = data
                fig.is_useful = bool(data.get("is_useful", True))
                fig.usefulness_reason = str(data.get("usefulness_reason", "")).strip()
                cache_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except QuotaExhaustedError:
                log.warning(
                    "Figure description quota exhausted for %s, skipping",
                    fig.figure_id,
                )
                fig.alt_text = ""
                fig.semantic_json = {}
                fig.is_useful = True
                fig.usefulness_reason = "quota_exhausted"
            except Exception as exc:
                log.warning(
                    "Figure description failed for %s: %s",
                    fig.figure_id, exc,
                )
                # Не отбрасываем по ошибке — лучше оставить картинку, чем потерять
                fig.alt_text = ""
                fig.semantic_json = {}
                fig.is_useful = True
                fig.usefulness_reason = "describe_failed"
        return figures

    def prune_unuseful(self, figures: List[Figure]) -> tuple[List[Figure], List[Figure]]:
        """Разделяет на (полезные, отброшенные). У отброшенных удаляет PNG с диска."""
        kept: List[Figure] = []
        dropped: List[Figure] = []
        for fig in figures:
            if fig.is_useful:
                kept.append(fig)
            else:
                dropped.append(fig)
                try:
                    Path(fig.file_path).unlink(missing_ok=True)
                except Exception as exc:
                    log.warning("Failed to delete unuseful figure %s: %s", fig.file_path, exc)
        if dropped:
            reasons: dict[str, int] = {}
            for f in dropped:
                reasons[f.usefulness_reason or "unknown"] = reasons.get(f.usefulness_reason or "unknown", 0) + 1
            log.info(
                "FigureExtractor: dropped %d unuseful figures → %s",
                len(dropped), reasons,
            )
        return kept, dropped

    # ── Internals ─────────────────────────────────────────────────────────

    def _extract_page(self, page, page_no: int, fitz) -> List[Figure]:
        """Возвращает все рисунки на странице, отсортированные top→bottom, left→right."""
        infos = page.get_image_info(xrefs=False)
        if not infos:
            return []

        # Фильтруем по минимальному размеру
        good: list[tuple[float, float, float, float]] = []
        for info in infos:
            bbox = info.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x0, y0, x1, y1 = bbox
            # bbox в pt; 1pt ≈ 1.33 px при 96 DPI; смотрим относительно рендерного DPI
            w_px = (x1 - x0) * _FIGURE_DPI / 72
            h_px = (y1 - y0) * _FIGURE_DPI / 72
            if w_px < _MIN_FIGURE_PX or h_px < _MIN_FIGURE_PX:
                continue
            good.append((x0, y0, x1, y1))

        if not good:
            return []

        # Дедуп идентичных bbox + сортировка визуально
        unique = sorted(set(good), key=lambda b: (round(b[1], 1), round(b[0], 1)))

        page_w = page.rect.width
        page_h = page.rect.height
        mat = fitz.Matrix(_FIGURE_DPI / 72, _FIGURE_DPI / 72)

        figures: List[Figure] = []
        for idx, (x0, y0, x1, y1) in enumerate(unique, start=1):
            # padding для подписей рисунков
            cx0 = max(0, x0 - _BBOX_PADDING_PT)
            cy0 = max(0, y0 - _BBOX_PADDING_PT)
            cx1 = min(page_w, x1 + _BBOX_PADDING_PT)
            cy1 = min(page_h, y1 + _BBOX_PADDING_PT)
            clip = fitz.Rect(cx0, cy0, cx1, cy1)

            try:
                pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csRGB)
            except Exception as exc:
                log.warning("Pixmap failed page %d bbox %s: %s", page_no, clip, exc)
                continue

            fid = figure_id_for(page_no, idx)
            file_path = self.figures_dir / f"{fid}.png"
            pix.save(str(file_path))

            figures.append(
                Figure(
                    figure_id=fid,
                    textbook_id=self.textbook_id,
                    page=page_no,
                    bbox=[round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    image_url=f"{self.url_prefix}/{self.textbook_id}/{fid}.png",
                    file_path=str(file_path),
                )
            )
        return figures


# ── Helpers ───────────────────────────────────────────────────────────────


def _safe_json(text: str) -> dict:
    """Парсит JSON, терпя markdown-обёртку."""
    text = text.strip()
    if text.startswith("```"):
        # snip markdown fence
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def figures_index_by_page(figures: List[Figure]) -> dict[int, List[Figure]]:
    """Группирует фигуры по странице для OCR-промпта."""
    idx: dict[int, List[Figure]] = {}
    for f in figures:
        idx.setdefault(f.page, []).append(f)
    return idx
