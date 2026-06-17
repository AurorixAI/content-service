"""Attach figure_refs to tasks from OCR [FIGURE id=...] markers in paragraph text."""
from __future__ import annotations

import re
from typing import Iterable

from src.pipeline.exercise_ranges import parse_exercise_num
from src.pipeline.models import ExtractedTask

FIGURE_MARKER_RE = re.compile(r'\[FIGURE id="([^"]+)"\]', re.IGNORECASE)
EXERCISE_BLOCK_RE = re.compile(r"(?:^|\n)\s*(\d+)\s*[.)]", re.MULTILINE)
FIGURE_HINT_RE = re.compile(
    r"рисун|рис\.|на чертеже|по графику|изображ|см\.\s*рис|fig-p|"
    r"по рисунку|на рис\.|смотри рис|чертёж|чертеж",
    re.IGNORECASE,
)
# «Начерти в тетради» — оффлайн; «по рисунку N» — онлайн если fig в тексте
_DRAW_IN_NOTEBOOK_RE = re.compile(
    r"начерт[иь].*тетрад|нарисуй.*тетрад|построй.*тетрад|"
    r"измерь линейк|вырежи|склей",
    re.IGNORECASE,
)


def _split_by_exercise(text: str) -> dict[int, str]:
    """Map exercise number → text block until next exercise header."""
    matches = list(EXERCISE_BLOCK_RE.finditer(text))
    blocks: dict[int, str] = {}
    for i, m in enumerate(matches):
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks[n] = text[start:end]
    return blocks


def _refs_in_text(text: str, valid_ids: set[str]) -> list[str]:
    seen: list[str] = []
    for fid in FIGURE_MARKER_RE.findall(text):
        if fid in valid_ids and fid not in seen:
            seen.append(fid)
    return seen


def _find_block_for_task(
    task: ExtractedTask,
    blocks: dict[int, str],
    paragraph_text: str,
) -> str:
    """Block text for task — by ex number or by question text overlap."""
    ex = parse_exercise_num(task.exercise_number)
    if ex is not None and ex in blocks:
        return blocks[ex]
    q = (task.question_text or "").strip()
    if len(q) >= 15:
        needle = q[: min(120, len(q))]
        for block in blocks.values():
            if needle in block:
                return block
        pos = paragraph_text.find(needle)
        if pos >= 0:
            return paragraph_text[max(0, pos - 200): pos + len(q) + 400]
    return ""


def _nearest_figure_refs(
    question: str,
    block: str,
    paragraph_text: str,
    valid: set[str],
) -> list[str]:
    """Find figure IDs near the task text."""
    refs = _refs_in_text(block, valid)
    if refs:
        return refs
    q = (question or "").strip()
    if len(q) >= 10:
        needle = q[:80]
        pos = paragraph_text.find(needle)
        if pos >= 0:
            window = paragraph_text[max(0, pos - 600): pos + len(q) + 600]
            refs = _refs_in_text(window, valid)
            if refs:
                return refs
    if FIGURE_HINT_RE.search(q) or FIGURE_HINT_RE.search(block):
        refs = _refs_in_text(block + "\n" + q, valid)
        if refs:
            return refs
        # все маркеры § — если задача явно про рисунок
        all_refs = _refs_in_text(paragraph_text, valid)
        if all_refs and FIGURE_HINT_RE.search(q):
            return all_refs[:3]
    return []


def is_figure_solvable_online(task: ExtractedTask) -> bool:
    """True if task uses a given figure (not draw-in-notebook)."""
    q = task.question_text or ""
    if _DRAW_IN_NOTEBOOK_RE.search(q):
        return False
    if not task.figure_refs:
        return False
    return bool(FIGURE_HINT_RE.search(q) or task.requires_figure)


def attach_figure_refs(
    tasks: Iterable[ExtractedTask],
    paragraph_text: str,
    figures_map: dict,
) -> list[ExtractedTask]:
    """Fill figure_refs / requires_figure when OCR markers or wording imply a figure."""
    if not figures_map:
        return list(tasks)

    valid = set(figures_map.keys())
    blocks = _split_by_exercise(paragraph_text)
    out: list[ExtractedTask] = []

    for task in tasks:
        q = task.question_text or ""
        block = _find_block_for_task(task, blocks, paragraph_text)

        refs = [r for r in (task.figure_refs or []) if r in valid]
        if not refs:
            refs = _nearest_figure_refs(q, block, paragraph_text, valid)

        if refs:
            task.figure_refs = refs
            task.requires_figure = True
            if is_figure_solvable_online(task):
                task.is_online_solvable = True
                task.skip_reason = ""
                if task.task_category == "with_drawing":
                    task.task_category = "standard"
            elif not task.is_online_solvable and task.skip_reason in (
                "missing_figure", "unknown_figure_ref", "",
            ):
                task.is_online_solvable = True
                task.skip_reason = ""
        out.append(task)

    return out
