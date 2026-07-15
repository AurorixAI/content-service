"""
ALGO V1 — Text Extraction Modules
src/pipeline/extraction.py

Три класса для извлечения контента из OCR-текста:
  • LegendExtractor  — легенда маркеров учебника (★, ●, ◆ …)
  • ParagraphSplitter — разбивка текста на параграфы по TOC
  • TaskExtractor     — извлечение задач из параграфа (Gemini Flash)
"""

import logging
import re
from typing import Dict, List, Optional

from src.pipeline.deepseek_client import (
    call_deepseek,
    get_deepseek_key,
    parse_json_response,
)
from src.pipeline.exercise_ranges import parse_exercise_num
from src.pipeline.models import ExtractedTask
from src.pipeline.quality import (
    extraction_model,
    extraction_temperature,
    is_high_quality,
    thinking_budget,
)

log = logging.getLogger("pipeline")
# LegendExtractor
# ============================================================================


class LegendExtractor:
    """Извлекает легенду условных обозначений из первых страниц учебника.

    Результат: ``{символ: категория}``
    Пример: ``{"★": "advanced", "●": "oral", "◆": "research"}``
    """

    CATEGORIES: Dict[str, str] = {
        "standard": "обычная задача (без маркера)",
        "advanced": "повышенной сложности (★, 🔴, и т.д.)",
        "olympiad": "олимпиадная / ★★",
        "oral": "устно / подумай (●, П)",
        "research": "исследование / проект (◆)",
        "project": "проект / практическая работа",
        "with_drawing": "задача с чертежом / рисунком (📐)",
    }

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or get_deepseek_key()

    def extract_legend(self, full_text: str, max_chars: int = 6000) -> Dict[str, str]:
        intro = full_text[:max_chars]
        prompt = self._build_prompt(intro)
        try:
            response = call_deepseek(
                prompt, temperature=0.0, max_tokens=2048
            )
            legend = self._parse(response)
            log.info("LegendExtractor: найдено %d маркеров: %s", len(legend), legend)
            return legend
        except Exception as e:
            log.warning("LegendExtractor: не удалось извлечь легенду: %s", e)
            return self._default()

    # ------------------------------------------------------------------

    def _build_prompt(self, text: str) -> str:
        cats = "\n".join(f"  - {k}: {v}" for k, v in self.CATEGORIES.items())
        return (
            "Ты — эксперт по российским школьным учебникам математики.\n\n"
            "Перед тобой начало учебника (введение, условные обозначения, предисловие).\n"
            "Извлеки ВСЕ условные обозначения (маркеры), которые используются для типов задач.\n\n"
            f"Текст:\n---\n{text}\n---\n\n"
            f"Категории:\n{cats}\n\n"
            "Верни JSON-объект {символ: категория}. Если не найдено — {}.\n"
            "Только JSON, без комментариев."
        )

    def _parse(self, response: str) -> Dict[str, str]:
        raw = parse_json_response(response)
        valid: Dict[str, str] = {}
        if not isinstance(raw, dict):
            return self._default()
        for marker, category in raw.items():
            if category in self.CATEGORIES:
                valid[marker] = category
            else:
                log.warning(
                    "LegendExtractor: неизвестная категория '%s' для '%s'",
                    category,
                    marker,
                )
                valid[marker] = "advanced"
        return valid

    @staticmethod
    def _default() -> Dict[str, str]:
        return {"★": "advanced", "*": "advanced", "●": "oral", "◆": "research"}


# ============================================================================
# ParagraphSplitter
# ============================================================================


class ParagraphSplitter:
    """Разбивает OCR-текст на параграфы по оглавлению (``textbook_toc``)."""

    def __init__(self, toc: List[Dict]):
        """``toc`` — список dict: ``{id, number, title, page_start, level}``."""
        self.toc = sorted(toc, key=lambda x: x.get("page_start", 0) or 0)

    def split(self, text: str) -> List[Dict]:
        """Возвращает ``[{toc_id, number, title, text}, …]``."""
        if not self.toc:
            return [
                {"toc_id": None, "number": "1", "title": "Весь текст", "text": text}
            ]

        paragraphs: List[Dict] = []
        lines = text.split("\n")

        for i, entry in enumerate(self.toc):
            pattern = self._make_pattern(entry)
            start_idx = self._find_line(lines, pattern)
            if start_idx is None:
                continue

            end_idx = len(lines)
            if i + 1 < len(self.toc):
                next_pat = self._make_pattern(self.toc[i + 1])
                nxt = self._find_line(lines, next_pat, start_from=start_idx + 1)
                if nxt is not None:
                    end_idx = nxt

            chunk = "\n".join(lines[start_idx:end_idx]).strip()
            if chunk:
                paragraphs.append(
                    {
                        "toc_id": entry.get("id"),
                        "number": entry.get("number", ""),
                        "title": entry.get("title", ""),
                        "text": chunk,
                    }
                )

        if not paragraphs:
            log.warning("Не удалось разбить текст по TOC, возвращаем целиком")
            return [
                {
                    "toc_id": None,
                    "number": "1",
                    "title": "Неразмеченный текст",
                    "text": text,
                }
            ]
        return paragraphs

    # ------------------------------------------------------------------

    @staticmethod
    def _make_pattern(entry: Dict) -> str:
        num = re.escape(entry.get("number", "").strip())
        title = re.escape(entry.get("title", "").strip()[:40])
        if num and title:
            return f"{num}.*{title}"
        return num or title

    @staticmethod
    def _find_line(
        lines: List[str], pattern: str, start_from: int = 0
    ) -> Optional[int]:
        if not pattern:
            return None
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return None
        for i in range(start_from, len(lines)):
            if regex.search(lines[i]):
                return i
        return None


# ============================================================================
# TaskExtractor
# ============================================================================


class TaskExtractor:
    """Извлекает задачи из текста параграфа через Gemini Flash."""

    def __init__(self, api_key: str = "", legend: Optional[Dict[str, str]] = None):
        self.legend = legend or {}

    def set_legend(self, legend: Dict[str, str]) -> None:
        self.legend = legend

    def extract(
        self,
        paragraph_text: str,
        paragraph_number: str = "",
        paragraph_title: str = "",
        toc_id: Optional[int] = None,
        exercise_num_range: Optional[tuple[int, int]] = None,
        only_exercises: Optional[list[int]] = None,
        *,
        content_first: bool = False,
        theme_stream: bool = False,
    ) -> List[ExtractedTask]:
        if not paragraph_text.strip():
            return []

        chunks = [c.strip() for c in re.split(r'\n+--- страница ---\n+', paragraph_text) if c.strip()]
        if not chunks:
            chunks = [paragraph_text]

        all_tasks = []
        for i, chunk in enumerate(chunks):
            log.info("§%s: извлечение из части %d/%d (%d символов)", paragraph_number, i + 1, len(chunks), len(chunk))
            
            if content_first or theme_stream:
                tasks = self._extract_once(
                    chunk, paragraph_number, paragraph_title,
                    toc_id, exercise_num_range,
                    content_first=content_first,
                    theme_stream=theme_stream,
                )
            elif only_exercises:
                tasks = self._extract_once(
                    chunk, paragraph_number, paragraph_title,
                    toc_id, exercise_num_range, only_exercises=only_exercises,
                )
            else:
                tasks = self._extract_once(
                    chunk, paragraph_number, paragraph_title,
                    toc_id, exercise_num_range,
                )
            all_tasks.extend(tasks)

        # Post-processing on the combined tasks
        if content_first or theme_stream:
            tasks = self._normalize_paragraph_task_numbers(all_tasks)
            log.info(
                "§%s: итого %d задач (%s)",
                paragraph_number, len(tasks),
                "theme-stream" if theme_stream else "content-first",
            )
            return tasks

        tasks = all_tasks
        if exercise_num_range:
            target_ex = set(only_exercises) if only_exercises else None
            tasks = self._fill_coverage_gaps(
                tasks, paragraph_text, paragraph_number,
                paragraph_title, toc_id, exercise_num_range,
                target_exercises=target_ex,
            )

        log.info("§%s: итого %d задач после coverage-fill", paragraph_number, len(tasks))
        return tasks

    def _extract_once(
        self,
        paragraph_text: str,
        paragraph_number: str,
        paragraph_title: str,
        toc_id: Optional[int],
        exercise_num_range: Optional[tuple[int, int]],
        *,
        only_exercises: Optional[list[int]] = None,
        content_first: bool = False,
        theme_stream: bool = False,
    ) -> List[ExtractedTask]:
        prompt = self._build_prompt(
            paragraph_text, paragraph_number, paragraph_title,
            exercise_num_range, only_exercises=only_exercises,
            content_first=content_first,
            theme_stream=theme_stream,
        )
        try:
            response = call_deepseek(
                prompt,
                temperature=extraction_temperature(),
                max_tokens=8192,
                system_prompt="Ты — эксперт по математике на ОНЛАЙН-платформе. Извлекай JSON-массив задач строго по правилам.",
            )
            tasks = self._parse(response, paragraph_number, paragraph_title, toc_id)
            return self._filter_by_exercise_range(
                tasks, exercise_num_range, paragraph_number,
                content_first=content_first or theme_stream,
            )
        except Exception as e:
            log.error("Ошибка извлечения §%s: %s", paragraph_number, e)
            return []

    def _fill_coverage_gaps(
        self,
        tasks: List[ExtractedTask],
        paragraph_text: str,
        paragraph_number: str,
        paragraph_title: str,
        toc_id: Optional[int],
        exercise_num_range: tuple[int, int],
        target_exercises: Optional[set[int]] = None,
    ) -> List[ExtractedTask]:
        lo, hi = exercise_num_range
        scope = target_exercises if target_exercises is not None else set(range(lo, hi + 1))
        found = {
            n for t in tasks
            if (n := parse_exercise_num(t.exercise_number)) is not None
        }
        missing = [n for n in sorted(scope) if n not in found]
        if not missing:
            return tasks

        log.info(
            "§%s: coverage gap — %d missing exercises, targeted retry",
            paragraph_number, len(missing),
        )
        merged = list(tasks)
        batch_size = 12
        max_rounds = 2
        for round_num in range(max_rounds):
            still_missing = [
                n for n in missing
                if not any(parse_exercise_num(t.exercise_number) == n for t in merged)
            ]
            if not still_missing:
                break
            for i in range(0, len(still_missing), batch_size):
                chunk = still_missing[i:i + batch_size]
                extra = self._extract_once(
                    paragraph_text, paragraph_number, paragraph_title,
                    toc_id, exercise_num_range, only_exercises=chunk,
                )
                merged = self._merge_by_exercise(merged, extra)
            log.info(
                "§%s: coverage round %d — %d tasks, still missing %d",
                paragraph_number, round_num + 1, len(merged),
                sum(1 for n in missing if not any(
                    parse_exercise_num(t.exercise_number) == n for t in merged
                )),
            )
        return merged

    @staticmethod
    def _normalize_paragraph_task_numbers(tasks: List[ExtractedTask]) -> List[ExtractedTask]:
        """Уникальные exercise_number внутри батча; локальная нумерация если номер не распознан."""
        seen: set[int] = set()
        next_local = 1
        for t in tasks:
            n = parse_exercise_num(t.exercise_number)
            if n is None or n in seen:
                while next_local in seen:
                    next_local += 1
                t.exercise_number = str(next_local)
                seen.add(next_local)
                next_local += 1
            else:
                seen.add(n)
        return tasks

    @staticmethod
    def _merge_by_exercise(
        existing: List[ExtractedTask],
        new_tasks: List[ExtractedTask],
    ) -> List[ExtractedTask]:
        by_ex: dict[int, ExtractedTask] = {}
        for t in existing:
            n = parse_exercise_num(t.exercise_number)
            if n is not None:
                by_ex[n] = t
        for t in new_tasks:
            n = parse_exercise_num(t.exercise_number)
            if n is None:
                continue
            prev = by_ex.get(n)
            if prev is None or len(t.question_text or "") > len(prev.question_text or ""):
                by_ex[n] = t
        return list(by_ex.values())

    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        text: str,
        number: str,
        title: str,
        exercise_num_range: Optional[tuple[int, int]] = None,
        *,
        only_exercises: Optional[list[int]] = None,
        content_first: bool = False,
        theme_stream: bool = False,
    ) -> str:
        if self.legend:
            legend_lines = "\n".join(f"  {m} → {c}" for m, c in self.legend.items())
            legend_section = (
                f"\nУСЛОВНЫЕ ОБОЗНАЧЕНИЯ УЧЕБНИКА:\n{legend_lines}\n"
                "Маркеры — только для is_online_solvable (oral/research/project/with_drawing → offline).\n"
                "★ и «повышенной сложности» НЕ задают difficulty — оцени A/B/C по содержанию задачи.\n"
                'task_marker — символ из учебника если есть, иначе "".\n'
                'task_category — "standard", либо oral/research/project/with_drawing если оффлайн.\n'
            )
        else:
            legend_section = (
                "\nМаркеры ★/●/◆ не влияют на difficulty — только на is_online_solvable.\n"
                'task_category="standard" для обычных задач.\n'
            )
        range_section = ""
        if theme_stream:
            range_section = (
                f"\n⚠ THEME-STREAM: извлеки ВСЕ онлайн-решаемые задачи блока «{title}» "
                f"(тема/раздел {number}).\n"
                "Включай упражнения из «Проверьте себя», «Тест I/II…» — это обычные задачи.\n"
                "exercise_number = номер из учебника как напечатано (сквозная нумерация: 30, 53…).\n"
                "Не фильтруй по номеру темы (1–2 ≠ упражнения 1–2).\n"
                "Подпункты 1) 2) 3) → ОТДЕЛЬНЫЕ задачи (N.1, N.2, N.3), ЕСЛИ корневая команда\n"
                "  «Вычислите/Решите/Найдите/Упростите/…» и каждый подпункт — свой пример.\n"
                "  Если варианты ответа А/Б/В/Г или «выберите/какое» → один MCQ task.\n"
                "Пропускай только: устные, начертить в тетради, исследования без ответа.\n"
                "\n🖼 ПРИОРИТЕТ — ЗАДАЧИ С РИСУНКАМИ:\n"
                "  • Задачи «по рисунку», «на рис.», «смотри чертёж» — ОБЯЗАТЕЛЬНО извлекай.\n"
                "  • В тексте есть [FIGURE id=\"fig-pN-K\"] — привяжи figure_refs к задаче.\n"
                "  • requires_figure=true, is_online_solvable=true (рисунок уже в системе).\n"
                "  • offline только если нужно НАЧЕРТИТЬ/ИЗМЕРИТЬ в тетради самому.\n"
            )
        elif content_first:
            range_section = (
                f"\n⚠ CONTENT-FIRST: извлеки ВСЕ задачи параграфа {number} «{title}», "
                "которые ученик может решить онлайн.\n"
                "Не пропускай задачу только потому, что не видишь её номер в учебнике.\n"
                "exercise_number — номер из учебника если явно указан, "
                "иначе порядковый номер по тексту (1, 2, 3…).\n"
                "Подпункты 1) 2) 3) → ОТДЕЛЬНЫЕ задачи (N.1, N.2, N.3), ЕСЛИ корневая команда\n"
                "  «Вычислите/Решите/Найдите/…» и каждый — свой пример.\n"
                "  Если варианты ответа А/Б/В/Г или «выберите/какое» → один MCQ task.\n"
                "Контрольные вопросы без числового/текстового ответа — пропускай.\n"
                "\n🖼 ПРИОРИТЕТ — ЗАДАЧИ С РИСУНКАМИ:\n"
                "  • Задачи «по рисунку», «на рис.», «смотри чертёж» — ОБЯЗАТЕЛЬНО извлекай.\n"
                "  • В тексте есть [FIGURE id=\"fig-pN-K\"] — привяжи figure_refs к задаче.\n"
                "  • requires_figure=true, is_online_solvable=true (рисунок уже в системе).\n"
                "  • НЕ помечай offline только потому что «нет рисунка» — ID есть в тексте.\n"
                "  • offline только если нужно НАЧЕРТИТЬ/ИЗМЕРИТЬ в тетради самому.\n"
            )
        elif only_exercises:
            nums = ", ".join(str(n) for n in only_exercises)
            range_section = (
                f"\n⚠ ИЗВЛЕКИ ТОЛЬКО упражнения №: {nums}.\n"
                "Пропусти все остальные номера.\n"
                "exercise_number = номер из учебника.\n"
                "Пункты 1), 2), 3), а), б), в) — ОТДЕЛЬНЫЕ задачи. exercise_number: «N.M».\n"
            )
        elif exercise_num_range:
            lo, hi = exercise_num_range
            range_section = (
                f"\n⚠ ДИАПАЗОН УПРАЖНЕНИЙ: извлекай ТОЛЬКО №{lo}–{hi} из этого параграфа.\n"
                f"exercise_number = номер из учебника (целое число {lo}…{hi}).\n"
                "Подпункты 1) 2) 3) → ОТДЕЛЬНЫЕ задачи (N.1, N.2, N.3), ЕСЛИ корневая команда\n"
                "  «Вычислите/Решите/…» и каждый — свой пример. Варианты А/Б/В/Г → MCQ.\n"
                "Контрольные вопросы и «Дополнительные упражнения» — пропускай.\n"
            )
        return (
            "Ты — эксперт по математике на ОНЛАЙН-платформе. Извлеки ВСЕ задачи из параграфа.\n\n"
            f"Параграф: {number} «{title}»\n{legend_section}{range_section}\n"
            f"Текст:\n---\n{text[:25000]}\n---\n\n"
            "Для каждой задачи верни JSON:\n"
            '{"exercise_number":"14","question_text":"...","question_latex":"...",'
            '"answer_raw":"11/12","answer_type":"fraction","difficulty":"B",'
            '"cognitive_load":"apply","task_marker":"","task_category":"standard",'
            '"image_description":"","is_online_solvable":true,"skip_reason":"",'
            '"requires_figure":false,"figure_refs":[]}\n\n'
            "answer_type — выбирай строго по математическому содержанию:\n"
            "  exact_number — единственное числовое значение (4, -7, √3, 2/3)\n"
            "  decimal      — десятичная дробь (1,75; -0,3)\n"
            "  fraction     — обыкновенная дробь (7/12; -5/8)\n"
            "  expression   — алгебраическое выражение (2x²+3x, (a+b)²)\n"
            "  equation_solution — одно или несколько уравнений/систем (x=2; y=-1)\n"
            "  inequality   — неравенство/промежуток (x>-2; x∈[1;3])\n"
            "  set          — выбор подмножества из ЯВНОГО списка объектов в условии\n"
            "                 (задача типа «найди среди чисел 1,38; 2,5; ... те, которые...»)\n"
            "  multiple_choice — вопрос с конечным числом вариантов А/Б/В или да/нет\n"
            "  text         — открытый ответ без единственного числового/алгебр. значения\n"
            "  coordinate   — точки на плоскости ((-2;3), (0;-1))\n"
            "difficulty — оцени САМ по математическому содержанию (не по ★/рубрикам учебника):\n"
            "  A — одно действие, шаблонное, очевидное\n"
            "  B — 2–3 шага, нужно понимание темы\n"
            "  C — многошаговая, нестандартная, составная\n"
            "task_category: standard, oral, research, project, with_drawing "
            "(oral/research/project/with_drawing → is_online_solvable=false)\n\n"
            "⚠ КРИТИЧЕСКИ ВАЖНО — is_online_solvable:\n"
            "  true  — ученик может решить в браузере и ввести ответ:\n"
            "          • число/дробь/выражение/уравнение/неравенство\n"
            "          • выбор из вариантов (multiple_choice)\n"
            "          • текстовое объяснение/доказательство теоремы (проверит LLM-grader)\n"
            "  false — ТРЕБУЕТ ОФФЛАЙН-действий (НЕ подходит для платформы):\n"
            "          • «проговори», «устно», «обсуди в классе»\n"
            "          • «начерти», «нарисуй в тетради», «измерь линейкой/транспортиром»\n"
            "          • «найди в учебнике/энциклопедии», «вырежь из бумаги»\n"
            "          • «сделай проект», «исследуй дома», «собери модель»\n"
            "          • НЕТ однозначного ответа (импровизация / творческая)\n"
            "  skip_reason — коротко русским (напр. «устный ответ», «требует чертеж»), если is_online_solvable=false\n"
            "  НЕ используй skip_reason для «номер отсутствует в тексте» — просто не включай такие упражнения в JSON.\n\n"
            "🖼 РИСУНКИ — requires_figure и figure_refs (ВЫСОКИЙ ПРИОРИТЕТ):\n"
            "  В тексте параграфа встречаются маркеры вида [FIGURE id=\"fig-pN-K\"].\n"
            "  Задачи «по рисунку», «на рис.», «по графику», «изображён» — ОБЯЗАТЕЛЬНО извлекай:\n"
            "     • requires_figure = true\n"
            "     • figure_refs = [\"fig-pN-K\", ...] — ID из ближайшего [FIGURE ...] маркера\n"
            "     • is_online_solvable = true (рисунок дан, ученик решает по нему)\n"
            "  offline только если нужно начертить/измерить САМОМУ в тетради.\n"
            "  Если задача чисто текстовая — requires_figure=false, figure_refs=[].\n"
            "  НЕ выдумывай figure_id, которых нет в тексте.\n\n"
            "━━━ ПРАВИЛО ПОДПУНКТОВ (ОЧЕНЬ ВАЖНО) ━━━\n"
            "Упражнение N с подпунктами 1) 2) 3) ... → ВСЕГДА делай отдельную task на каждый подпункт.\n"
            "  exercise_number = «N.1», «N.2», «N.3» и т.д.\n"
            "  question_text = только условие этого подпункта (без остальных).\n"
            "  Примеры команд, требующих разбивки: Вычислите / Решите / Найдите / Упростите /\n"
            "    Разложите / Выполните / Запишите / Докажите / Постройте / Составьте.\n\n"
            "ИСКЛЮЧЕНИЕ — НЕ разбивай, если подпункты — ВАРИАНТЫ ОТВЕТА (тест/MCQ):\n"
            "  • Вопрос «Какое из…», «Выберите…», «Укажите…», «Установите соответствие»\n"
            "    → один task, answer_type=multiple_choice, все варианты в question_text.\n"
            "  • Варианты помечены А) Б) В) Г) или A) B) C) D) → MCQ, не разбивать.\n"
            "  • Варианты помечены 1) 2) 3) НО вопрос типа «какое верно / выбери» → MCQ.\n\n"
            "Верни JSON-массив. Только JSON."
        )

    def _filter_by_exercise_range(
        self,
        tasks: List[ExtractedTask],
        exercise_num_range: Optional[tuple[int, int]],
        paragraph_number: str,
        *,
        content_first: bool = False,
    ) -> List[ExtractedTask]:
        tasks = [t for t in tasks if (t.question_text or "").strip()]
        if content_first or not exercise_num_range:
            return tasks
        lo, hi = exercise_num_range
        kept: List[ExtractedTask] = []
        for t in tasks:
            n = parse_exercise_num(t.exercise_number)
            if n is None or n < lo or n > hi:
                log.debug(
                    "§%s: skip exercise %s (outside %d–%d)",
                    paragraph_number, t.exercise_number, lo, hi,
                )
                continue
            kept.append(t)
        if len(kept) < len(tasks):
            log.info(
                "§%s: filtered %d→%d by exercise range %d–%d",
                paragraph_number, len(tasks), len(kept), lo, hi,
            )
        return kept

    def _parse(
        self,
        response: str,
        para_num: str,
        para_title: str,
        toc_id: Optional[int],
    ) -> List[ExtractedTask]:
        items = parse_json_response(response)
        if isinstance(items, dict):
            items = items.get("tasks", [items])
        if not isinstance(items, list):
            log.error("Неожиданный формат ответа: %s", type(items))
            return []

        offline_cats = {"oral", "research", "project", "with_drawing"}
        tasks: List[ExtractedTask] = []
        for i, item in enumerate(items):
            task_marker = str(item.get("task_marker", "")).strip()
            task_category = str(item.get("task_category", "standard")).strip()
            if task_category in ("advanced", "olympiad"):
                task_category = "standard"
            elif task_category not in offline_cats:
                task_category = "standard"

            is_online_solvable = bool(item.get("is_online_solvable", True))
            skip_reason = str(item.get("skip_reason", "")).strip()

            raw_refs = item.get("figure_refs") or []
            if isinstance(raw_refs, str):
                raw_refs = [raw_refs]
            figure_refs = [str(r).strip() for r in raw_refs if str(r).strip()]
            requires_figure = bool(item.get("requires_figure", False)) or bool(figure_refs)

            diff = str(item.get("difficulty", "B")).strip().upper()
            if diff not in ("A", "B", "C"):
                diff = "B"

            tasks.append(
                ExtractedTask(
                    temp_id=f"TEMP_{para_num}_{i + 1:03d}",
                    exercise_number=str(item.get("exercise_number", f"{i + 1}")),
                    paragraph_number=para_num,
                    paragraph_title=para_title,
                    question_text=item.get("question_text", ""),
                    question_latex=item.get("question_latex", ""),
                    answer_raw=str(item.get("answer_raw", "")),
                    answer_type=item.get("answer_type", "exact_number"),
                    difficulty=diff,
                    cognitive_load=item.get("cognitive_load", "apply"),
                    is_star=False,
                    task_marker=task_marker,
                    task_category=task_category,
                    image_description=item.get("image_description", ""),
                    is_online_solvable=is_online_solvable,
                    skip_reason=skip_reason,
                    requires_figure=requires_figure,
                    figure_refs=figure_refs,
                    toc_id=toc_id,
                    tags={
                        "exercise": item.get("exercise_number", ""),
                        "paragraph": para_num,
                        "marker": task_marker,
                        "category": task_category,
                    },
                )
            )
        return tasks
