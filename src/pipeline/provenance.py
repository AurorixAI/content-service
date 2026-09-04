"""
ALGO — Провенанс значений задачи (инвариант И1)
src/pipeline/provenance.py

Инвариант: **у каждого значимого поля есть источник и уверенность.**

До этого модуля `AIAnswerSolver.solve()` писал придуманный моделью ответ в то же
поле `answer_raw`, куда попадал ответ, напечатанный в книге. Ниже по течению
3 369 строк проверок (`answer_sympy_gate.py` + `answer_verify.py`) валидировали
эту догадку, **не зная, что это догадка**. Различить их постфактум нельзя — данные
не сохраняли различия.

Здесь вводится словарь источников и порядок их авторитета. Сам порядок применяется
в `answer_key.resolve_answer`; этот модуль — только словарь и правила сравнения,
чтобы у них было одно место определения.

Понятие авторитета источника в проекте уже было — `settings.smart_verify_answer_authority`
(`ai_first | textbook | ai_if_sympy_confirms`), но жило в конфиге и не имело
отражения в данных. Теперь имеет.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Источники ответа, по убыванию авторитета
# ---------------------------------------------------------------------------

#: Ответ напечатан в разделе «Ответы» книги и пришит точным матчем номера.
BOOK_KEY = "book_key"
#: Ответ извлечён из разобранного решения/решебника в теле книги.
BOOK_SOLUTION = "book_solution"
#: Ответ выведен SymPy из условия детерминированно (не «подтверждён», а выведен).
SYMPY_DERIVED = "sympy_derived"
#: Ответ придуман моделью. Фолбэк последней надежды.
AI_SOLVED = "ai_solved"
#: Ответа нет ни из одного источника.
ABSENT = "absent"

#: Порядок разрешения. Меньший индекс — выше авторитет.
ANSWER_AUTHORITY = (BOOK_KEY, BOOK_SOLUTION, SYMPY_DERIVED, AI_SOLVED, ABSENT)

_AUTHORITY_RANK = {src: i for i, src in enumerate(ANSWER_AUTHORITY)}

#: Источники, которые считаются «из книги» — по ним считается `answer_join_coverage`.
FROM_BOOK = frozenset({BOOK_KEY, BOOK_SOLUTION})

#: Источники, которые НЕ являются основанием для промоушена без ручной проверки.
NEEDS_HUMAN = frozenset({AI_SOLVED, ABSENT})


# ---------------------------------------------------------------------------
# Источники текста условия
# ---------------------------------------------------------------------------

#: Текст пришёл из распознавания страницы и не правился.
BOOK_OCR = "book_ocr"
#: Текст правился моделью (починка формул, склейка через разрыв страницы).
AI_REPAIRED = "ai_repaired"

TEXT_SOURCES = (BOOK_OCR, AI_REPAIRED)

#: Не источник, а признание: запись сделана до введения провенанса, и чем
#: подтверждён её текст или ответ — неизвестно. Отличается от `ABSENT`, который
#: означает «искали и не нашли». Ставится только бэкфилом миграции; конвейер
#: этого значения не пишет никогда — он всегда знает, откуда взял.
UNKNOWN = "unknown"



def answer_rank(source: str) -> int:
    """Ранг авторитета источника. Неизвестный источник — хуже любого известного."""
    return _AUTHORITY_RANK.get(source, len(ANSWER_AUTHORITY))


def outranks(candidate: str, incumbent: str) -> bool:
    """`candidate` авторитетнее, чем `incumbent`?

    Это единственное место, где сравнивается авторитет. Инвариант И2
    («сгенерированное никогда не перекрывает напечатанное») — прямое следствие:
    `outranks(AI_SOLVED, BOOK_KEY)` ложно, поэтому запись не произойдёт.
    """
    return answer_rank(candidate) < answer_rank(incumbent)


def is_from_book(source: str) -> bool:
    return source in FROM_BOOK


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


@dataclass
class Confidence:
    """Покомпонентная уверенность в задаче.

    Поля намеренно совпадают с тем, что уже отдаёт прототип
    (`confidence: {ocr, structure}` в `mathocr` tasks.json) плюс `answer`,
    которого там не было. Совпадение не случайно — это упрощает перенос
    выгрузки прототипа без потери сигнала.

    `None` означает **не измерено** и не равно `0.0` («измерено и плохо»).
    Та же дисциплина, что в `src/eval/metrics.py`.
    """

    ocr: Optional[float] = None
    structure: Optional[float] = None
    answer: Optional[float] = None

    def as_dict(self) -> Dict[str, Optional[float]]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "Confidence":
        if not isinstance(raw, dict):
            return cls()
        def _f(key: str) -> Optional[float]:
            v = raw.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None
            return float(v)
        return cls(ocr=_f("ocr"), structure=_f("structure"), answer=_f("answer"))

    def min_measured(self) -> Optional[float]:
        """Минимум по измеренным компонентам. None — если не измерено ничего."""
        vals = [v for v in (self.ocr, self.structure, self.answer) if v is not None]
        return min(vals) if vals else None


@dataclass
class Provenance:
    """Полный провенанс одной задачи — то, что едет в staging рядом с задачей."""

    answer_source: str = ABSENT
    text_source: str = BOOK_OCR
    confidence: Confidence = field(default_factory=Confidence)
    #: Страница книги, с которой взят ответ (для `book_key` — страница раздела «Ответы»).
    answer_source_page: Optional[int] = None
    #: Свободные пометки стадий: почему поле такое, какое есть.
    notes: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "answer_source": self.answer_source,
            "text_source": self.text_source,
            "confidence": self.confidence.as_dict(),
            "answer_source_page": self.answer_source_page,
            "notes": dict(self.notes),
        }
