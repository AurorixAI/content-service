"""Словарь значений в коде обязан совпадать с CHECK в миграции.

Тест заведён после сверки 2026-09-04, где нашлось три разных представления
о допустимых `answer_type` в одном проекте, и два из них были неверны.
Класс дефекта не новый: B10 (код читает колонку, которой не создаёт ни одна
миграция) и B12 (код пишет статус, которого не принимает CHECK) — то же самое.

Проверка статическая: разбирает текст baseline-миграции, база не нужна,
поэтому работает в CI.
"""
import pathlib
import re

from src.pipeline import schema_vocab as vocab

BASELINE = (
    pathlib.Path(__file__).resolve().parent.parent
    / "alembic" / "versions" / "a1b2c3d4e5f6_baseline.py"
)


def _check_values(column: str) -> set[str]:
    """Значения из `CHECK (<column> IN ( … ))` в тексте миграции."""
    sql = BASELINE.read_text(encoding="utf-8")
    m = re.search(
        rf"CHECK\s*\(\s*{re.escape(column)}\s+IN\s*\((.*?)\)\s*\)",
        sql, re.S,
    )
    assert m, f"в миграции не найден CHECK для {column}"
    return set(re.findall(r"'([^']+)'", m.group(1)))


class TestVocabMatchesMigration:
    def test_answer_types(self):
        assert set(vocab.ANSWER_TYPES) == _check_values("answer_type")

    def test_cognitive_loads(self):
        assert set(vocab.COGNITIVE_LOADS) == _check_values("cognitive_load")

    def test_difficulties(self):
        assert set(vocab.DIFFICULTIES) == _check_values("difficulty")

    def test_defaults_are_themselves_allowed(self):
        assert vocab.DEFAULT_ANSWER_TYPE in vocab.ANSWER_TYPES
        assert vocab.DEFAULT_COGNITIVE_LOAD in vocab.COGNITIVE_LOADS
        assert vocab.DEFAULT_DIFFICULTY in vocab.DIFFICULTIES


class TestClamp:
    def test_value_outside_vocabulary_falls_back(self):
        # `boolean` клэмп в orchestrator раньше пропускал, а CHECK отвергал.
        assert vocab.clamp("boolean", vocab.ANSWER_TYPES, vocab.DEFAULT_ANSWER_TYPE) == "exact_number"

    def test_valid_value_survives(self):
        # `equation_solution` раньше схлопывался в `exact_number`, теряя смысл.
        assert vocab.clamp(
            "equation_solution", vocab.ANSWER_TYPES, vocab.DEFAULT_ANSWER_TYPE,
        ) == "equation_solution"

    def test_empty_and_none(self):
        for bad in ("", "   ", None):
            assert vocab.clamp(bad, vocab.ANSWER_TYPES, vocab.DEFAULT_ANSWER_TYPE) == "exact_number"

    def test_long_phrase_from_model(self):
        phrase = "это задача на нахождение точного числового ответа"
        assert vocab.clamp(phrase, vocab.ANSWER_TYPES, vocab.DEFAULT_ANSWER_TYPE) == "exact_number"


class TestClampDifficulty:
    """B40: соседние поля клэмпились, `difficulty` бралось сырым.

    У `tasks_staging` CHECK на неё нет, у `tasks_master` есть — модель,
    вернувшая «средняя» вместо «B», проходила staging и падала на вставке в
    master. `except Exception` в `promote()` считал это просто `failed`, и
    задача оставалась в карантине без внятной причины.
    """

    def test_phrase_from_model_falls_back(self):
        assert vocab.clamp_difficulty("средняя") == vocab.DEFAULT_DIFFICULTY

    def test_lowercase_letter_keeps_its_meaning(self):
        # Схлопнуть «c» в умолчание значило бы потерять смысл там, где терять
        # нечего: `irt_difficulty` считается ровно из этой буквы.
        assert vocab.clamp_difficulty("c") == "C"

    def test_valid_value_survives(self):
        assert vocab.clamp_difficulty("A") == "A"

    def test_empty_and_none(self):
        for bad in ("", "   ", None):
            assert vocab.clamp_difficulty(bad) == vocab.DEFAULT_DIFFICULTY

    def test_result_is_always_acceptable_to_the_check(self):
        for raw in ("A", "b", "C", "средняя", None, 7, "B "):
            assert vocab.clamp_difficulty(raw) in vocab.DIFFICULTIES


class TestIrtParams:
    """B39: формула жила только в `db_writer`, новый шов записи её потерял."""

    def test_levels_are_distinguishable(self):
        bs = [vocab.irt_params(d, "exact_number")["irt_difficulty"] for d in "ABC"]
        assert bs == sorted(bs) and len(set(bs)) == 3

    def test_multiple_choice_can_be_guessed(self):
        assert vocab.irt_params("B", "multiple_choice")["irt_guessing"] > 0

    def test_open_answer_cannot(self):
        assert vocab.irt_params("B", "exact_number")["irt_guessing"] == 0.0

    def test_unclamped_input_does_not_crash(self):
        # Параметры не должны зависеть от того, прошло ли значение клэмп раньше.
        assert vocab.irt_params("средняя", "exact_number")["irt_difficulty"] == (
            vocab.irt_params(vocab.DEFAULT_DIFFICULTY, "exact_number")["irt_difficulty"]
        )


class TestAllWritersAgree:
    def test_db_writer_uses_the_shared_vocabulary(self):
        """Копии словаря — то, как разошлись предыдущие три."""
        src = (
            pathlib.Path(__file__).resolve().parent.parent
            / "src" / "pipeline" / "db_writer.py"
        ).read_text(encoding="utf-8")
        assert "_VALID_ANSWER_TYPE = vocab.ANSWER_TYPES" in src
        assert "_VALID_COGLOAD = vocab.COGNITIVE_LOADS" in src

    def test_orchestrator_no_longer_keeps_its_own(self):
        src = (
            pathlib.Path(__file__).resolve().parent.parent
            / "src" / "pipeline" / "orchestrator.py"
        ).read_text(encoding="utf-8")
        assert "_ALLOWED_ANSWER_TYPE" not in src
        assert "_ALLOWED_COGNITIVE" not in src

    def test_difficulty_is_clamped_by_every_producer(self):
        """Своя копия правила в каждом производителе задач — это и был B40."""
        root = pathlib.Path(__file__).resolve().parent.parent / "src" / "pipeline"
        for name in ("orchestrator.py", "extraction.py"):
            src = (root / name).read_text(encoding="utf-8")
            assert "clamp_difficulty" in src, f"{name} берёт difficulty сырым"

    def test_irt_formula_has_a_single_home(self):
        src = (
            pathlib.Path(__file__).resolve().parent.parent
            / "src" / "pipeline" / "db_writer.py"
        ).read_text(encoding="utf-8")
        assert "vocab.irt_params(" in src
        assert '{"A": -1.0, "B": 0.5, "C": 1.5}' not in src
