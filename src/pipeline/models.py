"""
ALGO V1 — Pipeline Data Models
src/pipeline/models.py

Dataclasses, используемые всеми модулями конвейера.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# ExtractedTask — центральная единица конвейера
# ---------------------------------------------------------------------------


@dataclass
class ExtractedTask:
    """Задача, извлечённая из текста учебника."""

    temp_id: str = ""
    exercise_number: str = ""
    page: int = 0
    paragraph_number: str = ""
    paragraph_title: str = ""

    question_text: str = ""
    question_latex: str = ""
    answer_raw: str = ""
    answer_type: str = "exact_number"
    # exact_number, expression, multiple_choice, text, fraction,
    # equation_solution, set, coordinate, inequality
    answer_options: Optional[List[str]] = None

    difficulty: str = "B"  # A, B, C
    cognitive_load: str = "apply"  # recall, apply, analyze
    is_star: bool = False  # ★ задача
    task_marker: str = ""  # оригинальный символ-маркер
    task_category: str = "standard"
    # standard, advanced, olympiad, oral, research, project, with_drawing
    image_description: str = ""

    # --- Заполняются на этапах обработки ---
    sympy_verified: bool = False
    sympy_answer: str = ""
    sympy_confidence: float = 0.0
    distractors: Optional[List[str]] = None
    distractor_meta: Optional[List[Dict]] = (
        None  # [{value, error_type, explanation, plausibility, broken_step}]
    )

    # --- Online-platform filter ---
    # is_online_solvable: может ли ученик решить задачу онлайн
    #   TRUE  — число/дробь/выражение/multiple_choice/текстовый ответ (проверит LLM-grader)
    #   FALSE — устно/чертёж/исследование в учебнике/физ. инструменты — НЕ пишется в tasks_master
    is_online_solvable: bool = True
    skip_reason: str = ""  # заполняется если is_online_solvable=False

    # --- Figures (рисунки/графики/чертежи) ---
    # requires_figure: без визуала задача нерешаема
    # figure_refs: ID изображений в task_figures (напр. ["fig-p12-1"])
    requires_figure: bool = False
    figure_refs: List[str] = field(default_factory=list)

    # --- Дуальный маппинг ---
    # skill_id может быть None — задачи без маппинга на ядро (textbook-only)
    skill_id: Optional[str] = None
    toc_id: Optional[int] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    mapping_confidence: float = 0.0


# ---------------------------------------------------------------------------
# Figure — рисунок/график/чертёж, извлечённый из PDF
# ---------------------------------------------------------------------------


@dataclass
class Figure:
    """Изображение из учебника с метаданными для AI."""

    figure_id: str            # канонический ID: fig-p{page}-{idx}
    textbook_id: str          # UUID учебника
    page: int                 # 1-based номер страницы PDF
    bbox: List[float]         # [x0, y0, x1, y1] в PDF-координатах
    image_url: str            # относительный URL (/api/v1/figures/<tb>/<id>.png)
    file_path: str = ""       # локальный путь к PNG на диске (не сохраняется в БД)
    alt_text: str = ""        # короткое описание для screen-readers
    semantic_json: Dict[str, Any] = field(default_factory=dict)  # структура для AI
    # --- Usefulness filter (аналог is_online_solvable, но для картинок) ---
    # is_useful=False — фото детей, портрет, орнамент, обложка, декор — пустых к задаче
    # is_useful=True  — геометрия, график, система координат, диаграмма, таблица с данными
    is_useful: bool = True
    usefulness_reason: str = ""  # math_diagram | function_plot | photo | portrait | decorative | ...


# ---------------------------------------------------------------------------
# DistractorResult
# ---------------------------------------------------------------------------


@dataclass
class DistractorResult:
    """Результат генерации одного дистрактора с метаданными."""

    value: str
    error_type: str  # sign_error, off_by_one, transfer_error, …
    explanation: str  # Почему ученик мог так ответить
    plausibility: float  # 0–1, насколько правдоподобный


# ---------------------------------------------------------------------------
# TemplateResult
# ---------------------------------------------------------------------------


@dataclass
class TemplateResult:
    """Результат генерации параметрического шаблона."""

    template_string: str
    template_latex: Optional[str]
    parameters: List[str]
    constraints: Dict[str, Dict[str, Any]]
    answer_formula: str
    generation_method: str
    quality_score: float
    tested_combinations: int
