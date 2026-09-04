"""Словари значений, которые принимает база.

Зачем отдельный модуль. Один и тот же перечень «допустимых answer_type» жил
в трёх местах и в двух из них был неверен (сверка 2026-09-04):

* `db_writer._VALID_ANSWER_TYPE` — 12 значений, совпадал с базой;
* `orchestrator._ALLOWED_ANSWER_TYPE` — 8 значений, расходился **в обе
  стороны**: пропускал `boolean`, `interval`, `ordered_list`, которых CHECK
  не принимает (вставка упала бы), и схлопывал в `exact_number` семь типов,
  которые база принимает (`equation_solution`, `fraction`, `coordinate`,
  `inequality`, `decimal`, `multiple_values`, `text`) — то есть терял смысл
  задачи там, где терять было нечего;
* `staging.py` — не проверял ничего.

То же с `cognitive_load`: клэмп разрешал `evaluate` и `create`, а CHECK знает
только `recall`/`apply`/`analyze`.

Источник истины — миграция, а не этот файл. `tests/test_schema_vocab.py`
сверяет константы с текстом `CREATE TABLE` в `a1b2c3d4e5f6_baseline.py` и
падает при расхождении, поэтому правка миграции без правки словаря не пройдёт
CI. Проверка статическая: разбирает файл миграции, база не нужна.
"""

from __future__ import annotations

#: `tasks_master.answer_type` — CHECK из baseline-миграции.
ANSWER_TYPES: frozenset[str] = frozenset({
    "exact_number", "expression", "multiple_choice", "text",
    "fraction", "equation_solution", "set", "coordinate",
    "inequality", "decimal", "open_text", "multiple_values",
})
DEFAULT_ANSWER_TYPE = "exact_number"

#: `tasks_master.cognitive_load`.
COGNITIVE_LOADS: frozenset[str] = frozenset({"recall", "apply", "analyze"})
DEFAULT_COGNITIVE_LOAD = "apply"

#: `tasks_master.difficulty`.
DIFFICULTIES: frozenset[str] = frozenset({"A", "B", "C"})
DEFAULT_DIFFICULTY = "B"


def clamp(value: object, allowed: frozenset[str], default: str) -> str:
    """Значение из словаря, иначе — умолчание.

    Клэмп существует ради одного: модель иногда возвращает вместо токена целую
    фразу, а колонка в базе — `varchar(20)` с CHECK. Молча подставить умолчание
    здесь правильнее, чем уронить вставку, но набор обязан совпадать с базой —
    иначе клэмп пропускает то, что база отвергнет, и не спасает ни от чего.
    """
    text = str(value or "").strip()
    return text if text in allowed else default


def clamp_difficulty(value: object) -> str:
    """`difficulty` из словаря A/B/C. Регистр приводится, а не отбрасывается.

    Отдельная функция, а не голый `clamp`, из-за B40: соседние поля в
    `_dict_to_task` клэмпились, а `difficulty` брался сырым. У `tasks_staging`
    CHECK на неё нет, у `tasks_master` есть — модель, вернувшая «средняя»
    вместо «B», проходила staging и падала на вставке в master, где
    `except Exception` в `promote()` считал её просто `failed`. Задача
    оставалась в карантине без внятной причины.

    Регистр важен: модель возвращает и «b», и «B». Без приведения «b»
    схлопывалось бы в умолчание, то есть теряло бы смысл там, где терять
    нечего — а `irt_difficulty` считается ровно из этой буквы (`irt_params`).
    """
    return clamp(str(value or "").strip().upper(), DIFFICULTIES, DEFAULT_DIFFICULTY)


#: IRT 3PL по уровню сложности. Единственное место, где `A`/`B`/`C`
#: превращается в число: раньше формула жила только в `db_writer`, а новый шов
#: записи (staging → promote) её потерял целиком (B39). Для CAT это значило,
#: что у каждой задачи банка одинаковая `irt_difficulty` и подбор под theta
#: перестаёт различать задачи.
_IRT_B_BY_DIFFICULTY: dict[str, float] = {"A": -1.0, "B": 0.5, "C": 1.5}

#: Дискриминация: одна на все задачи, пока её нечем калибровать.
IRT_DEFAULT_DISCRIMINATION = 1.0
#: Угадывание. Ненулевое только там, где угадать физически можно.
IRT_MCQ_GUESSING = 0.2


def irt_params(difficulty: object, answer_type: object) -> dict[str, float]:
    """Параметры 3PL для задачи: `{discrimination, difficulty, guessing}`.

    `difficulty` клэмпится здесь же — параметры не должны зависеть от того,
    прошло ли значение клэмп раньше по пути.
    """
    return {
        "irt_discrimination": IRT_DEFAULT_DISCRIMINATION,
        "irt_difficulty": _IRT_B_BY_DIFFICULTY[clamp_difficulty(difficulty)],
        "irt_guessing": (
            IRT_MCQ_GUESSING
            if str(answer_type or "").strip() == "multiple_choice"
            else 0.0
        ),
    }
