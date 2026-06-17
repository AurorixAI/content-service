"""Content Service — Digitization Orchestrator

Full pipeline per textbook:
  OCR → Legend → Split → Extract → Validate → Enrich → Distractors → Classify → Write

Reports progress to Redis via JobStateManager at each step.
Each paragraph is processed independently so a failure mid-book does not
lose already-written tasks.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, List, Optional

from src.core.config import get_settings
from src.core.exceptions import PipelineError
from src.core.job_state import JobStateManager, PipelineStep
from src.pipeline.classification import SkeletonTextbookMapper
from src.pipeline.db_writer import DBWriter
from src.pipeline.enrichment import AIAnswerSolver
from src.pipeline.extraction import LegendExtractor, ParagraphSplitter, TaskExtractor
from src.pipeline.figures import FigureExtractor, figures_index_by_page
from src.pipeline.exercise_ranges import (
    exercise_range,
    parse_exercise_num,
    task_id_prefix,
)
from src.pipeline.figure_links import attach_figure_refs, is_figure_solvable_online
from src.pipeline.models import ExtractedTask, Figure
from src.pipeline.ocr import GeminiVisionOCR
from src.pipeline.ocr_utils import is_usable_ocr_text
from src.pipeline.pipeline_mode import pipeline_mode
from src.pipeline.quality import filter_quality_tasks
from src.pipeline.theme_stream.matcher import TocMatcher
from src.pipeline.theme_stream.segmenter import _is_back_matter, build_segments_from_pages
from src.pipeline.validation import SymPySolver

log = logging.getLogger(__name__)


# ── Online-platform filter ───────────────────────────────────────────────
# Задачи, которые НЕЛЬЗЯ решить онлайн (устно, начертить в тетради, измерить
# линейкой, собрать модель и т.п.) — НЕ пишутся в tasks_master. Они бесполезны
# и для диагностики, и для модуля экзаменов: платформа онлайн-only.
# Текстовые ответы (доказательства, объяснения теорем) разрешены — их
# проверяет LLM-grader.

_OFFLINE_KEYWORDS = (
    "проговор", "произнеси вслух", "обсуди в клас", "обсуди с учител",
    "начерти", "нарисуй в тетрад", "построй в тетрад", "перенеси в тетрад",
    "измерь линейк", "измерь транспорт", "с помощью циркул",
    "найди в учебник", "найди в энциклопеди", "найди в интернет",
    "вырежи", "склей", "сделай модел", "собери модел",
    "сделай проект", "подготовь проект", "исследуй дома",
    "взвесь", "сосчитай предмет", "посчитай в комнат",
)

_OFFLINE_CATEGORIES = {"oral", "research", "project", "with_drawing"}

# LLM часто ставит is_online_solvable=false с «номер отсутствует в тексте» —
# это ошибка extraction, не оффлайн-задача.
_FALSE_OFFLINE_SKIP_FRAGMENTS = (
    "отсутствует в тексте",
    "отсутствуют в тексте",
    "номер отсутствует",
    "номера отсутствуют",
    "задача отсутствует",
    "задачи отсутствуют",
    "отсутствует в предоставленном",
    "отсутствуют в предоставленном",
    "пропущено в нумерации",
    "нет в тексте",
    "отсутствует изображение",
    "нет изображения",
    "изображение отсутствует",
    "рисунок отсутствует",
)


def _skip_reason_is_false_offline(skip_reason: str) -> bool:
    r = (skip_reason or "").lower()
    return any(p in r for p in _FALSE_OFFLINE_SKIP_FRAGMENTS)


def _looks_like_extraction_meta(question_text: str) -> bool:
    q = (question_text or "").strip().lower()
    if len(q) < 15:
        return True
    meta_hints = (
        "отсутствуют в", "отсутствует в", "нет в тексте",
        "не найден", "не представлен", "не включен",
    )
    return any(h in q for h in meta_hints)


def _is_extraction_miss_placeholder(task: ExtractedTask) -> bool:
    """Placeholder от LLM («упражнения X–Y отсутствуют») — не offline и не задача."""
    if task.is_online_solvable:
        return False
    if not _skip_reason_is_false_offline(task.skip_reason):
        return False
    return _looks_like_extraction_meta(task.question_text)


def _recover_false_offline(task: ExtractedTask) -> None:
    """Снимает ложный offline-флаг, если текст задачи реальный."""
    if task.is_online_solvable:
        return
    if not _skip_reason_is_false_offline(task.skip_reason):
        return
    if _looks_like_extraction_meta(task.question_text):
        return
    task.is_online_solvable = True
    task.skip_reason = ""


def _is_offline_task(task: ExtractedTask, known_figure_ids: set[str] | None = None) -> tuple[bool, str]:
    """Hard-rules фильтр поверх LLM-решения. Возвращает (offline?, причина)."""
    if not task.is_online_solvable:
        if _skip_reason_is_false_offline(task.skip_reason):
            return True, task.skip_reason or "extraction_miss_marked_offline"
        return True, task.skip_reason or "llm_marked_offline"
    if task.task_category in _OFFLINE_CATEGORIES:
        return True, f"category:{task.task_category}"
    ql = (task.question_text or "").lower()
    for kw in _OFFLINE_KEYWORDS:
        if kw in ql:
            return True, f"keyword:{kw}"
    # НЕ фильтруем по пустому answer_raw: в учебнике ответы в конце книги,
    # не в тексте задачи. Ответ вычисляет enricher (через Gemini Pro).
    # Требует рисунок, но ничего не привязано — без визуала нерешаема
    if task.requires_figure and not task.figure_refs:
        return True, "missing_figure"
    # Рисунок привязан — задача «по рисунку» решаема онлайн
    if task.figure_refs and known_figure_ids:
        if any(ref in known_figure_ids for ref in task.figure_refs):
            if is_figure_solvable_online(task):
                return False, ""
    # Ссылки есть, но ни одна не существует в базе фигур
    if task.requires_figure and known_figure_ids is not None:
        if not any(ref in known_figure_ids for ref in task.figure_refs):
            return True, "unknown_figure_ref"
    return False, ""


from src.pipeline.dedup import is_duplicate_question, question_fingerprint


class DigitizationOrchestrator:
    """Runs the full digitization pipeline for one textbook, streaming
    progress updates into the job state manager.

    Args:
        job_id: Redis job identifier (used for progress tracking).
        textbook_id: UUID of the textbook row in the DB.
        class_level: Grade level (5–11).
    """

    def __init__(
        self,
        job_id: str,
        textbook_id: str,
        class_level: int,
        *,
        content_first: bool = False,
        target_paragraphs: set[str] | None = None,
    ) -> None:
        self.job_id = job_id
        self.textbook_id = textbook_id
        self.class_level = class_level
        self.content_first = content_first
        self.target_paragraphs = target_paragraphs
        self.state = JobStateManager()
        self.writer = DBWriter()
        # Заполняется после figure extraction; используется фильтром
        self._known_figure_ids: set[str] = set()

    # ── Public entry points ───────────────────────────────────────────────

    def run_pdf(self, pdf_path: str) -> int:
        from src.pipeline.pipeline_mode import pipeline_mode

        if pipeline_mode(self.textbook_id) == "theme_stream":
            return self.run_pdf_theme_stream(pdf_path)
        return self._run_pdf_page_based(pdf_path)

    def _run_pdf_page_based(self, pdf_path: str) -> int:
        """Per-paragraph pipeline: PDF → DB.  Returns total tasks written.

        Strategy: drive the entire pipeline from the TOC. For each leaf
        paragraph (level >= 2), process only its page range:
          figures → describe → prune → write → OCR pages → extract → … → write.

        Benefits over the old bulk approach:
          * Progress is saved per paragraph (any failure preserves everything done so far).
          * Calls to Gemini are paced by the global rate limiter — no thundering 429s.
          * Resume is trivial: paragraphs already written to tasks_master are skipped.
        """
        log.info("[%s] Starting per-paragraph PDF pipeline: %s", self.job_id, pdf_path)
        self.writer.update_digitization_status(self.textbook_id, "processing", 0.0)

        # ── Load TOC and compute (page_start, page_end) per paragraph ──────
        toc = self.writer.load_toc(self.textbook_id)
        if not toc:
            raise RuntimeError(
                f"TOC is empty for textbook {self.textbook_id}; run update-toc first"
            )

        # Determine PDF length once for the last paragraph's page_end
        try:
            import fitz  # PyMuPDF
            with fitz.open(pdf_path) as doc:
                pdf_total_pages = len(doc)
        except Exception as exc:
            log.warning("[%s] Could not read PDF length: %s", self.job_id, exc)
            pdf_total_pages = 10_000

        # Sort by page_start; page_end = next_start - 1 (or pdf_total_pages for last)
        # Drop entries with no page_start at all — we can't process them.
        toc_with_pages = [t for t in toc if t.get("page_start") is not None]
        toc_sorted = sorted(toc_with_pages, key=lambda t: t["page_start"])
        # page_end for each entry = page_start of the NEXT entry whose page_start is strictly greater
        for i, entry in enumerate(toc_sorted):
            if entry.get("page_end") is not None:
                continue
            cur_start = entry["page_start"]
            next_start: Optional[int] = None
            for j in range(i + 1, len(toc_sorted)):
                ns = toc_sorted[j]["page_start"]
                if ns is not None and ns > cur_start:
                    next_start = ns
                    break
            entry["page_end"] = (next_start - 1) if next_start else pdf_total_pages

        # True leaf nodes: entries that are not parents of any other entry.
        # This handles 2-level (skip level 1) and 3-level (skip level 1+2) TOCs.
        parent_ids = {t.get("parent_id") for t in toc_sorted if t.get("parent_id") is not None}
        candidate_leaves = [t for t in toc_sorted if t.get("id") not in parent_ids]
        # Always skip pure top-level structural chapters (level 1 with no pages worth processing)
        leaves = [t for t in candidate_leaves if (t.get("level") or 1) >= 2]
        if not leaves:
            leaves = toc_sorted  # fallback: treat the whole TOC as leaves
        log.info(
            "[%s] TOC: %d total, %d leaf paragraphs to process",
            self.job_id, len(toc_sorted), len(leaves),
        )
        self.state.set_paragraphs_total(self.job_id, len(leaves))

        # ── Legend: extract once from the first ~10 pages (lookup table) ──
        resume_from = get_settings().resume_from_paragraph
        self.state.set_step(self.job_id, PipelineStep.LEGEND)
        if resume_from and resume_from > 1:
            log.info("[%s] resume_from_paragraph=%d — skip legend OCR", self.job_id, resume_from)
            legend = {}
        else:
            try:
                ocr_first = GeminiVisionOCR()
                head_text = ocr_first.process_pages(
                    pdf_path, 1, min(10, pdf_total_pages),
                    figures_by_page={},
                )
                legend = LegendExtractor().extract_legend(head_text)
            except Exception as exc:
                log.warning("[%s] Legend extraction failed (continuing without): %s",
                            self.job_id, exc)
                legend = {}
        log.info("[%s] Legend: %d markers", self.job_id, len(legend))

        # Reusable workers — created once, used per paragraph
        fig_extractor = FigureExtractor(self.textbook_id)
        ocr_worker = GeminiVisionOCR()
        extractor = TaskExtractor(legend=legend)
        skills_json = self._load_skills_json()
        mapper = SkeletonTextbookMapper(skills_json=skills_json)

        # Pre-load already-known figure ids (resume case)
        self._known_figure_ids = self.writer.load_figure_ids(self.textbook_id)

        self.state.set_step(self.job_id, PipelineStep.EXTRACT)

        total_written = 0
        failed_paras: list[str] = []
        if resume_from:
            log.info("[%s] resume_from_paragraph=%d — skipping §1..§%d",
                     self.job_id, resume_from, resume_from - 1)

        for idx, entry in enumerate(leaves):
            number = entry.get("number") or str(idx)
            title = entry.get("title") or ""
            toc_id = entry.get("id")
            p_start = entry.get("page_start") or 1
            p_end = entry.get("page_end") or p_start

            try:
                para_n = int(str(number).split(".")[0])
            except ValueError:
                para_n = 0
            if resume_from and para_n < resume_from:
                log.info(
                    "[%s] §%s [p.%d-%d]: SKIP (resume_from §%d)",
                    self.job_id, number, p_start, p_end, resume_from,
                )
                self.state.increment_paragraph(self.job_id, 0)
                continue

            if self.target_paragraphs is not None:
                para_key = str(number).split(".")[0]
                if number not in self.target_paragraphs and para_key not in self.target_paragraphs:
                    self.state.increment_paragraph(self.job_id, 0)
                    continue

            only_exercises: list[int] | None = None
            if self.content_first:
                in_db = self.writer.load_paragraph_exercise_numbers(
                    self.textbook_id, number,
                )
                log.info(
                    "[%s] §%s [p.%d-%d]: content-first re-extract "
                    "(%d tasks already in DB)",
                    self.job_id, number, p_start, p_end, len(in_db),
                )
            else:
                # ── Resume: skip § only when exercise-range coverage is complete ──
                missing_ex = self.writer.missing_exercises(self.textbook_id, number)
                if missing_ex is not None:
                    if not missing_ex:
                        log.info(
                            "[%s] §%s [p.%d-%d]: SKIP (coverage complete)",
                            self.job_id, number, p_start, p_end,
                        )
                        self.state.increment_paragraph(self.job_id, 0)
                        continue
                    in_db = self.writer.load_paragraph_exercise_numbers(
                        self.textbook_id, number,
                    )
                    if in_db:
                        only_exercises = missing_ex
                        log.info(
                            "[%s] §%s [p.%d-%d]: gap-fill %d missing exercises: %s%s",
                            self.job_id, number, p_start, p_end,
                            len(missing_ex),
                            missing_ex[:12],
                            "..." if len(missing_ex) > 12 else "",
                        )
                    else:
                        log.info(
                            "[%s] §%s [p.%d-%d]: first pass full extract "
                            "(%d ex expected from range)",
                            self.job_id, number, p_start, p_end, len(missing_ex),
                        )
                elif self.writer.paragraph_has_tasks(toc_id):
                    log.info("[%s] §%s [p.%d-%d]: SKIP (already in DB)",
                             self.job_id, number, p_start, p_end)
                    self.state.increment_paragraph(self.job_id, 0)
                    continue

            try:
                written = self._process_paragraph_pages(
                    entry=entry,
                    pdf_path=pdf_path,
                    fig_extractor=fig_extractor,
                    ocr_worker=ocr_worker,
                    extractor=extractor,
                    mapper=mapper,
                    only_exercises=only_exercises,
                )
            except Exception as exc:
                log.error(
                    "[%s] §%s [p.%d-%d]: paragraph FAILED (skipped): %s",
                    self.job_id, number, p_start, p_end, exc, exc_info=True,
                )
                failed_paras.append(number)
                self.state.increment_paragraph_failed(self.job_id)
                written = 0
            total_written += written

            pct = round((idx + 1) / len(leaves) * 100, 1) if leaves else 0
            self.writer.update_digitization_status(
                self.textbook_id, "processing", pct, total_written
            )
            log.info(
                "[%s] §%s (%s) [p.%d-%d] DONE: +%d (total %d) — progress %.1f%%",
                self.job_id, number, title[:40], p_start, p_end, written,
                total_written, pct,
            )

        if failed_paras:
            log.warning(
                "[%s] Completed with %d failed paragraph(s): %s",
                self.job_id, len(failed_paras), failed_paras,
            )

        self.writer.update_digitization_status(self.textbook_id, "done", 100.0, total_written)
        return total_written

    def run_pdf_theme_stream(self, pdf_path: str) -> int:
        """Sequential OCR + theme-header segmentation → extract per matched TOC §."""
        log.info("[%s] Starting theme-stream PDF pipeline: %s", self.job_id, pdf_path)
        self.writer.update_digitization_status(self.textbook_id, "processing", 0.0)

        toc = self.writer.load_toc(self.textbook_id)
        if not toc:
            raise RuntimeError(
                f"TOC is empty for textbook {self.textbook_id}; run update-toc first"
            )

        try:
            import fitz
            with fitz.open(pdf_path) as doc:
                pdf_total_pages = len(doc)
        except Exception as exc:
            log.warning("[%s] Could not read PDF length: %s", self.job_id, exc)
            pdf_total_pages = 240

        parent_ids = {t.get("parent_id") for t in toc if t.get("parent_id")}
        leaves = [t for t in toc if t.get("id") not in parent_ids and (t.get("level") or 1) >= 2]
        if not leaves:
            leaves = [t for t in toc if (t.get("level") or 1) >= 2]
        leaves.sort(key=lambda t: t.get("sort_order") or 0)

        matcher = TocMatcher(leaves)
        default_toc = next(
            (l for l in leaves if str(l.get("number") or "") in ("1", "1–7")),
            leaves[0] if leaves else None,
        )

        resume_from = get_settings().resume_from_paragraph
        self.state.set_step(self.job_id, PipelineStep.LEGEND)
        legend: dict = {}
        try:
            ocr_head = GeminiVisionOCR()
            head_text = ocr_head.process_pages(pdf_path, 1, min(10, pdf_total_pages), figures_by_page={})
            legend = LegendExtractor().extract_legend(head_text)
        except Exception as exc:
            log.warning("[%s] Legend extraction failed: %s", self.job_id, exc)

        fig_extractor = FigureExtractor(self.textbook_id)
        ocr_worker = GeminiVisionOCR()
        extractor = TaskExtractor(legend=legend)
        skills_json = self._load_skills_json()
        mapper = SkeletonTextbookMapper(skills_json=skills_json)
        self._known_figure_ids = self.writer.load_figure_ids(self.textbook_id)

        content_start = 3
        content_end = min(pdf_total_pages - 10, 232)
        pages_data: list[tuple[int, str]] = []

        cached_pages = ocr_worker.count_cached_pages(pdf_path, content_start, content_end)
        total_pages = content_end - content_start + 1
        log.info(
            "[%s] theme-stream OCR cache: %d/%d pages on disk (missing → Gemini)",
            self.job_id, cached_pages, total_pages,
        )

        self.state.set_step(self.job_id, PipelineStep.OCR)
        for page in range(content_start, content_end + 1):
            text = ocr_worker.process_pages(pdf_path, page, page, figures_by_page={})
            if not is_usable_ocr_text(text):
                ocr_worker.invalidate_pages_cache(pdf_path, page, page)
                for attempt in range(1, 4):
                    if attempt > 1:
                        time.sleep(25 * attempt)
                    text = ocr_worker.process_pages(
                        pdf_path, page, page, figures_by_page={}, force_refresh=True,
                    )
                    if is_usable_ocr_text(text):
                        break
                    ocr_worker.invalidate_pages_cache(pdf_path, page, page)
            if not is_usable_ocr_text(text):
                log.warning("[%s] page %d: OCR unusable after retries, skip", self.job_id, page)
                continue
            if _is_back_matter(text, page, pdf_total_pages):
                log.info("[%s] back matter at page %d — stop scan", self.job_id, page)
                break
            pages_data.append((page, text))
            if page % 20 == 0:
                log.info("[%s] theme-stream OCR progress: page %d", self.job_id, page)

        segments = build_segments_from_pages(
            pages_data, matcher, default_toc=default_toc,
        )
        log.info("[%s] theme-stream: %d segments from %d pages", self.job_id, len(segments), len(pages_data))

        self.state.set_step(self.job_id, PipelineStep.EXTRACT)
        self.state.set_paragraphs_total(self.job_id, len(segments))

        total_written = 0
        failed: list[str] = []

        for idx, seg in enumerate(segments):
            entry = seg.toc_entry
            if not entry:
                log.warning(
                    "[%s] segment p.%d-%d: no TOC match (%s)",
                    self.job_id, seg.page_start, seg.page_end,
                    seg.marker.line if seg.marker else "?",
                )
                continue

            number = entry.get("number") or "?"
            if resume_from:
                try:
                    if int(str(number).split("-")[0]) < resume_from:
                        self.state.increment_paragraph(self.job_id, 0)
                        continue
                except ValueError:
                    pass

            if self.writer.paragraph_has_tasks(entry.get("id")):
                log.info("[%s] §%s: SKIP (already in DB)", self.job_id, number)
                self.state.increment_paragraph(self.job_id, 0)
                continue

            proc_entry = dict(entry)
            proc_entry["page_start"] = seg.page_start
            proc_entry["page_end"] = seg.page_end

            try:
                written = self._process_paragraph_pages(
                    proc_entry,
                    pdf_path,
                    fig_extractor,
                    ocr_worker,
                    extractor,
                    mapper,
                    text_override=seg.combined_text,
                    theme_stream=True,
                    toc_binding_confidence=seg.match_confidence,
                )
            except Exception as exc:
                log.error(
                    "[%s] §%s theme-segment FAILED: %s",
                    self.job_id, number, exc, exc_info=True,
                )
                failed.append(str(number))
                self.state.increment_paragraph_failed(self.job_id)
                written = 0

            total_written += written
            pct = round((idx + 1) / len(segments) * 100, 1) if segments else 0
            self.writer.update_digitization_status(
                self.textbook_id, "processing", pct, total_written,
            )

        if failed:
            log.warning(
                "[%s] theme-stream: %d failed segment(s): %s",
                self.job_id, len(failed), failed,
            )

        self.writer.update_digitization_status(self.textbook_id, "done", 100.0, total_written)
        return total_written

    def _process_paragraph_pages(
        self,
        entry: dict,
        pdf_path: str,
        fig_extractor: FigureExtractor,
        ocr_worker: GeminiVisionOCR,
        extractor: TaskExtractor,
        mapper: SkeletonTextbookMapper,
        only_exercises: list[int] | None = None,
        *,
        text_override: str | None = None,
        theme_stream: bool = False,
        toc_binding_confidence: float = 0.0,
    ) -> int:
        """Full per-paragraph pipeline for one TOC entry (its page range)."""
        number = entry.get("number") or "?"
        title = entry.get("title") or ""
        toc_id = entry.get("id")
        p_start = entry.get("page_start") or 1
        p_end = entry.get("page_end") or p_start

        # 1. Figures from page range
        figures = fig_extractor.extract_pages(pdf_path, p_start, p_end)
        figures_map: dict[str, Figure] = {}
        if figures:
            figures = fig_extractor.describe_all(figures)
            kept, dropped = fig_extractor.prune_unuseful(figures)
            if dropped:
                self.writer.increment_figures_skipped(self.textbook_id, len(dropped))
            if kept:
                # Register figure ids for the offline filter — do NOT write to
                # DB yet. Figures are written lazily after task extraction so
                # only figures actually referenced by tasks are persisted.
                self._known_figure_ids.update(f.figure_id for f in kept)
                figures_map = {f.figure_id: f for f in kept}
            figures = kept

        # 2. OCR (or reuse pre-OCR segment text from theme-stream)
        fig_index = figures_index_by_page(figures)
        if text_override is not None:
            text_content = text_override
        else:
            text_content = ocr_worker.process_pages(
                pdf_path, p_start, p_end,
                figures_by_page=fig_index,
            )
            if not is_usable_ocr_text(text_content):
                log.warning(
                    "[%s] §%s: OCR unusable (%d chars) — invalidate + retry",
                    self.job_id, number, len(text_content or ""),
                )
                ocr_worker.invalidate_pages_cache(pdf_path, p_start, p_end)
                text_content = ocr_worker.process_pages(
                    pdf_path, p_start, p_end,
                    figures_by_page=fig_index,
                    force_refresh=True,
                )

        if not is_usable_ocr_text(text_content):
            raise PipelineError(
                f"§{number}: OCR failed for pages {p_start}-{p_end} "
                f"({len(text_content or '')} chars)"
            )

        # 3. Skip ParagraphSplitter — the OCR output already IS the paragraph
        para = {
            "toc_id": toc_id,
            "number": number,
            "title": title,
            "text": text_content,
        }
        written, extracted = self._process_paragraph(
            para, extractor, mapper, figures_map=figures_map,
            only_exercises=only_exercises,
            theme_stream=theme_stream,
            toc_binding_confidence=toc_binding_confidence,
        )

        if written == 0 and extracted == 0:
            had_before = self.writer.paragraph_has_tasks(toc_id)
            if (self.content_first or theme_stream) and had_before:
                log.info(
                    "[%s] §%s: content-first — no new tasks found (%d already in DB)",
                    self.job_id, number, len(
                        self.writer.load_paragraph_exercise_numbers(
                            self.textbook_id, number,
                        )
                    ),
                )
                return 0
            ex_range = exercise_range(self.textbook_id, number)
            hint = f" (expected ex {ex_range[0]}–{ex_range[1]})" if ex_range else ""
            if theme_stream:
                hint = ""
            if had_before and only_exercises:
                log.warning(
                    "[%s] §%s: gap-fill found 0 new online tasks for %s",
                    self.job_id, number, only_exercises[:10],
                )
                return 0
            if theme_stream:
                log.info(
                    "[%s] §%s: theme-stream — no online tasks in segment",
                    self.job_id, number,
                )
                return 0
            raise PipelineError(
                f"§{number}: OCR ok ({len(text_content)} chars) but 0 tasks extracted{hint}"
            )
        return written

    def run_json(self, json_path: str) -> int:
        """Import from manually prepared JSON file → DB.  Returns tasks written."""
        log.info("[%s] Starting JSON import: %s", self.job_id, json_path)
        self.writer.update_digitization_status(self.textbook_id, "processing", 0.0)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get("tasks", [])
        tasks: List[ExtractedTask] = [self._dict_to_task(item) for item in items]
        log.info("[%s] Loaded %d tasks from JSON", self.job_id, len(tasks))

        self.state.set_step(self.job_id, PipelineStep.VALIDATE)
        tasks = self._validate_batch(tasks)

        self.state.set_step(self.job_id, PipelineStep.ENRICH)
        tasks = self._enrich_batch(tasks)

        self.state.set_step(self.job_id, PipelineStep.DISTRACTORS)
        tasks = self._distractor_batch(tasks)

        self.state.set_step(self.job_id, PipelineStep.CLASSIFY)
        # Load skills once — reuse mapper across all tasks in the batch
        skills_json = self._load_skills_json()
        mapper = SkeletonTextbookMapper(skills_json=skills_json)
        tasks = mapper.map_batch(tasks)

        self.state.set_step(self.job_id, PipelineStep.WRITE)
        written = self.writer.write_batch(
            tasks,
            self.textbook_id,
            self.class_level,
            prefix=task_id_prefix(self.textbook_id, self.class_level),
        )
        self.state.increment_written(self.job_id, written)
        self.writer.update_digitization_status(self.textbook_id, "done", 100.0, written)
        return written

    # ── Internal: text pipeline ───────────────────────────────────────────

    def _run_text(self, text: str) -> int:
        # Если фигуры были уже записаны раньше (резюме / json import) — подтянем из БД
        if not self._known_figure_ids:
            self._known_figure_ids = self.writer.load_figure_ids(self.textbook_id)

        # 2. Legend
        self.state.set_step(self.job_id, PipelineStep.LEGEND)
        legend = LegendExtractor().extract_legend(text)
        log.info("[%s] Legend: %d markers", self.job_id, len(legend))

        # 3. TOC from DB + split
        self.state.set_step(self.job_id, PipelineStep.SPLIT)
        toc = self.writer.load_toc(self.textbook_id)
        paragraphs = ParagraphSplitter(toc).split(text)
        log.info("[%s] Split: %d paragraphs", self.job_id, len(paragraphs))

        self.state.set_paragraphs_total(self.job_id, len(paragraphs))

        # 4–9. Process paragraph by paragraph
        self.state.set_step(self.job_id, PipelineStep.EXTRACT)

        extractor = TaskExtractor(legend=legend)
        skills_json = self._load_skills_json()
        mapper = SkeletonTextbookMapper(skills_json=skills_json)

        total_written = 0
        failed_paras: list[str] = []
        total_paras = len(paragraphs)
        for idx, para in enumerate(paragraphs):
            try:
                written, _ = self._process_paragraph(para, extractor, mapper)
            except Exception as exc:
                number = para.get("number", str(idx))
                log.error(
                    "[%s] §%s: paragraph FAILED (skipped): %s",
                    self.job_id, number, exc, exc_info=True,
                )
                failed_paras.append(number)
                self.state.increment_paragraph_failed(self.job_id)
                written = 0
            total_written += written
            # Update progress in textbooks table every paragraph
            pct = round((idx + 1) / total_paras * 100, 1) if total_paras else 0
            self.writer.update_digitization_status(
                self.textbook_id, "processing", pct, total_written
            )

        if failed_paras:
            log.warning(
                "[%s] Completed with %d failed paragraph(s): %s",
                self.job_id, len(failed_paras), failed_paras,
            )
        return total_written

    def _process_paragraph(
        self,
        para: dict,
        extractor: TaskExtractor,
        mapper: SkeletonTextbookMapper,
        figures_map: dict[str, Figure] | None = None,
        only_exercises: list[int] | None = None,
        *,
        theme_stream: bool = False,
        toc_binding_confidence: float = 0.0,
    ) -> tuple[int, int]:
        """Returns (tasks_written, tasks_extracted_before_offline_filter)."""
        number = para.get("number", "?")
        log.info("[%s] §%s: extracting", self.job_id, number)

        # Extract
        ex_range = None if theme_stream else exercise_range(self.textbook_id, number)
        tasks = extractor.extract(
            para["text"],
            number,
            para.get("title", ""),
            para.get("toc_id"),
            exercise_num_range=ex_range,
            only_exercises=only_exercises,
            content_first=self.content_first and not theme_stream,
            theme_stream=theme_stream,
        )
        if toc_binding_confidence > 0:
            for t in tasks:
                t.tags["toc_binding_confidence"] = round(toc_binding_confidence, 3)
                t.tags["pipeline_mode"] = "theme_stream"
        extracted_count = len(tasks)
        if not tasks:
            self.state.increment_paragraph(self.job_id, 0)
            return 0, 0

        if figures_map:
            tasks = attach_figure_refs(tasks, para["text"], figures_map)
            for t in tasks:
                if is_figure_solvable_online(t):
                    t.is_online_solvable = True
                    t.skip_reason = ""
                    if t.task_category == "with_drawing":
                        t.task_category = "standard"

        # 🚫 Filter offline-only tasks
        tasks, skipped = self._filter_online_solvable(tasks, number)
        if skipped:
            self.writer.increment_tasks_skipped(self.textbook_id, skipped)
        if not tasks:
            log.info(
                "[%s] §%s: all %d extracted tasks offline — skip write",
                self.job_id, number, extracted_count,
            )
            self.state.increment_paragraph(self.job_id, 0)
            return 0, extracted_count

        existing = self.writer.load_paragraph_exercise_numbers(self.textbook_id, number)
        if self.content_first:
            known_q = self.writer.load_paragraph_question_fingerprints(
                self.textbook_id, number,
            )
            before = len(tasks)
            tasks = [
                t for t in tasks
                if not is_duplicate_question(t.question_text or "", known_q)
            ]
            if before - len(tasks):
                log.info(
                    "[%s] §%s: skip %d duplicate questions (text match)",
                    self.job_id, number, before - len(tasks),
                )
            ex_range = exercise_range(self.textbook_id, number)
            tasks = self._assign_exercise_numbers_in_range(
                tasks, existing, ex_range, number,
            )
        elif existing:
            before = len(tasks)
            tasks = [
                t for t in tasks
                if (n := parse_exercise_num(t.exercise_number)) is None or n not in existing
            ]
            skipped_existing = before - len(tasks)
            if skipped_existing:
                log.info(
                    "[%s] §%s: skip %d tasks already in DB (no overwrite)",
                    self.job_id, number, skipped_existing,
                )
        if not tasks:
            self.state.increment_paragraph(self.job_id, 0)
            return 0, extracted_count

        # ── Validate → Enrich → Distractors → Classify → Write (chunked) ──
        # Process in small chunks to avoid Gemini rate-limit bursts and write
        # partial results early (if something crashes later, earlier chunks survive).
        chunk_size = get_settings().enrich_chunk_size or len(tasks)
        total_written = 0
        figures_written = False

        for chunk_start in range(0, len(tasks), chunk_size):
            chunk = tasks[chunk_start: chunk_start + chunk_size]

            chunk = self._validate_batch(chunk)
            chunk = self._enrich_batch(chunk, figures_map=figures_map)
            chunk = self._distractor_batch(chunk)
            chunk = mapper.map_batch(chunk)

            chunk, q_dropped = filter_quality_tasks(chunk)
            if q_dropped:
                log.info(
                    "[%s] §%s chunk %d: quality gate dropped %d tasks",
                    self.job_id, number, chunk_start // chunk_size + 1, q_dropped,
                )
            if not chunk:
                continue

            # Write figures once (only on first chunk that survives quality gate)
            if not figures_written and figures_map:
                referenced_ids = {
                    fid
                    for task in chunk
                    for fid in (task.figure_refs or [])
                    if fid in figures_map
                }
                if referenced_ids:
                    ref_figures = [figures_map[fid] for fid in referenced_ids]
                    self.writer.write_figures(ref_figures, self.textbook_id)
                    log.info(
                        "[%s] §%s: figures saved %d/%d",
                        self.job_id, number, len(ref_figures), len(figures_map),
                    )
                figures_written = True

            written_chunk = self.writer.write_batch(
                chunk,
                self.textbook_id,
                self.class_level,
                prefix=task_id_prefix(self.textbook_id, self.class_level),
            )
            total_written += written_chunk
            if len(tasks) > chunk_size:
                log.info(
                    "[%s] §%s chunk %d/%d: wrote %d tasks",
                    self.job_id, number,
                    chunk_start // chunk_size + 1,
                    (len(tasks) + chunk_size - 1) // chunk_size,
                    written_chunk,
                )

        self.state.increment_paragraph(self.job_id, len(tasks))
        self.state.increment_written(self.job_id, total_written)

        log.info(
            "[%s] §%s: %d extracted, %d written",
            self.job_id, number, len(tasks), total_written,
        )
        written = total_written
        return written, extracted_count

    # ── Batch helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _validate_batch(tasks: List[ExtractedTask]) -> List[ExtractedTask]:
        solver = SymPySolver()
        result = []
        for t in tasks:
            try:
                result.append(solver.verify(t))
            except Exception as exc:
                log.warning("Validation failed for task %s: %s", t.temp_id, exc)
                result.append(t)  # keep original, skip validation
        return result

    def _enrich_batch(
        self,
        tasks: List[ExtractedTask],
        figures_map: dict | None = None,
    ) -> List[ExtractedTask]:
        """Решает задачи без ответа через Gemini. Задачи с ответом не трогает."""
        solver = AIAnswerSolver()
        result = []
        for t in tasks:
            fig_ctx = ""
            if figures_map and t.figure_refs:
                parts = []
                for fid in t.figure_refs:
                    fig = figures_map.get(fid)
                    if fig and getattr(fig, "alt_text", None):
                        parts.append(f"[{fid}] {fig.alt_text}")
                fig_ctx = "\n".join(parts)
            try:
                result.append(solver.solve(t, figure_context=fig_ctx))
            except Exception as exc:
                log.warning("Solve failed for task %s: %s", t.temp_id, exc)
                result.append(t)
        return result

    @staticmethod
    def _distractor_batch(tasks: List[ExtractedTask]) -> List[ExtractedTask]:
        from src.pipeline.distractors import generate_distractors
        result = []
        for t in tasks:
            try:
                result.append(generate_distractors(t))
            except Exception as exc:
                log.warning("Distractors failed for task %s: %s", t.temp_id, exc)
                result.append(t)  # keep original, skip distractors
        return result

    def _filter_online_solvable(
        self,
        tasks: List[ExtractedTask],
        paragraph_number: str,
    ) -> tuple[List[ExtractedTask], int]:
        """Удаляет задачи, которые нельзя решить онлайн.

        Возвращает (оставшиеся, число пропущенных).
        """
        kept: List[ExtractedTask] = []
        reasons: dict[str, int] = {}
        extraction_miss = 0
        recovered = 0
        for t in tasks:
            if _is_extraction_miss_placeholder(t):
                extraction_miss += 1
                continue
            was_offline = not t.is_online_solvable
            _recover_false_offline(t)
            if was_offline and t.is_online_solvable:
                recovered += 1
            offline, reason = _is_offline_task(t, self._known_figure_ids)
            if offline:
                reasons[reason] = reasons.get(reason, 0) + 1
            else:
                kept.append(t)
        skipped = len(tasks) - len(kept) - extraction_miss
        if extraction_miss:
            log.info(
                "[%s] §%s: dropped %d extraction-miss placeholders (not offline)",
                self.job_id, paragraph_number, extraction_miss,
            )
        if recovered:
            log.info(
                "[%s] §%s: recovered %d tasks from false-offline skip_reason",
                self.job_id, paragraph_number, recovered,
            )
        if skipped:
            log.info(
                "[%s] §%s: skipped %d offline tasks → %s",
                self.job_id, paragraph_number, skipped, reasons,
            )
        return kept, skipped

    @staticmethod
    def _assign_exercise_numbers_in_range(
        tasks: List[ExtractedTask],
        existing: set[int],
        ex_range: tuple[int, int] | None,
        paragraph_number: str,
    ) -> List[ExtractedTask]:
        """Назначает номера только внутри диапазона §; не создаёт 682+ при range 677–681."""
        if not ex_range:
            return DigitizationOrchestrator._assign_new_exercise_numbers(tasks, existing)
        lo, hi = ex_range
        allowed = set(range(lo, hi + 1))
        missing = sorted(allowed - existing)
        kept: List[ExtractedTask] = []
        used = set(existing)
        for t in tasks:
            n = parse_exercise_num(t.exercise_number)
            if n is not None and n in allowed and n not in used:
                kept.append(t)
                used.add(n)
                if n in missing:
                    missing.remove(n)
                continue
            if not missing:
                log.info(
                    "§%s: drop task — range %d–%d full, no slot for new task",
                    paragraph_number, lo, hi,
                )
                continue
            slot = missing.pop(0)
            t.exercise_number = str(slot)
            kept.append(t)
            used.add(slot)
        return kept

    @staticmethod
    def _assign_new_exercise_numbers(
        tasks: List[ExtractedTask],
        existing: set[int],
    ) -> List[ExtractedTask]:
        """Назначает номера новым задачам, не конфликтуя с уже записанными в §."""
        used = set(existing)
        next_n = (max(used) + 1) if used else 1
        for t in tasks:
            n = parse_exercise_num(t.exercise_number)
            if n is None or n in used:
                while next_n in used:
                    next_n += 1
                t.exercise_number = str(next_n)
                used.add(next_n)
                next_n += 1
            else:
                used.add(n)
        return tasks

    def _classify_batch(self, tasks: List[ExtractedTask]) -> List[ExtractedTask]:
        skills_json = self._load_skills_json()
        mapper = SkeletonTextbookMapper(skills_json=skills_json)
        return mapper.map_batch(tasks)

    def _load_skills_json(self) -> str:
        """Load skills from DB and serialise to JSON string for the mapper."""
        import json
        skills = self.writer.load_skills(self.class_level)
        return json.dumps(skills, ensure_ascii=False)

    # ── Conversion ────────────────────────────────────────────────────────

    # Allowed values for varchar(20) DB columns. AI sometimes returns a long
    # phrase instead of a single token — we clamp to the safe default.
    _ALLOWED_ANSWER_TYPE = {"exact_number", "multiple_choice", "open_text", "interval", "expression", "set", "boolean", "ordered_list"}
    _ALLOWED_COGNITIVE = {"recall", "apply", "analyze", "evaluate", "create"}
    _ALLOWED_CATEGORY = {"standard", "star", "olympiad", "applied", "research", "oral"}

    @staticmethod
    def _clamp(value, allowed: set, default: str) -> str:
        v = str(value or default).strip().lower()
        if v in allowed:
            return v
        return default

    @staticmethod
    def _dict_to_task(item: dict) -> ExtractedTask:
        return ExtractedTask(
            temp_id=item.get("temp_id", ""),
            exercise_number=str(item.get("exercise_number", "")),
            paragraph_number=str(item.get("paragraph_number", "")),
            paragraph_title=item.get("paragraph_title", ""),
            question_text=item.get("question_text", ""),
            question_latex=item.get("question_latex", ""),
            answer_raw=str(item.get("answer_raw", item.get("correct_answer", ""))),
            answer_type=PipelineOrchestrator._clamp(item.get("answer_type"), PipelineOrchestrator._ALLOWED_ANSWER_TYPE, "exact_number"),
            difficulty=item.get("difficulty", "B"),
            cognitive_load=PipelineOrchestrator._clamp(item.get("cognitive_load"), PipelineOrchestrator._ALLOWED_COGNITIVE, "apply"),
            is_star=bool(item.get("is_star", False)),
            task_marker=item.get("task_marker", ""),
            task_category=PipelineOrchestrator._clamp(item.get("task_category"), PipelineOrchestrator._ALLOWED_CATEGORY, "standard"),
            skill_id=item.get("skill_id", ""),
            toc_id=item.get("toc_id"),
            tags=item.get("tags", {}),
        )
