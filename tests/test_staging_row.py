"""Шов записи staging → master: что новый путь потерял относительно `db_writer`.

Три дефекта одного происхождения (B39, B41, B44). Переход на И3 переносил
ответственность за запись из `db_writer` в `staging.py` + `promote()`, и часть
обязанностей при переносе выпала — молча, потому что ни один из них не был
покрыт тестом. Прогон при этом был зелёный.
"""

import pytest

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline import staging as S
from src.pipeline.models import ExtractedTask


def task(**kw) -> ExtractedTask:
    base = dict(
        question_text="Вычислите площадь круга радиуса пять",
        answer_raw="42",
        answer_source=prov.BOOK_KEY,
        answer_type="exact_number",
        difficulty="B",
    )
    base.update(kw)
    return ExtractedTask(**base)


def row(t: ExtractedTask) -> dict:
    return S._row(t, G.Verdict(), "G8_TB_1_1", "tb-1", 8, "run1")


# ---------------------------------------------------------------------------
# B39 — IRT-параметры
# ---------------------------------------------------------------------------


class TestIrtReachesStaging:
    """Значение не терялось на записи — оно не доезжало до staging вообще."""

    def test_difficulty_is_reflected_in_irt_b(self):
        # Ровно то, ради чего параметр существует: три уровня сложности не
        # должны быть для CAT одной и той же задачей.
        bs = [row(task(difficulty=d))["irt_difficulty"] for d in ("A", "B", "C")]
        assert bs == sorted(bs) and len(set(bs)) == 3

    def test_multiple_choice_gets_nonzero_guessing(self):
        mcq = row(task(answer_type="multiple_choice"))
        assert mcq["irt_guessing"] > 0

    def test_open_answer_cannot_be_guessed(self):
        assert row(task(answer_type="exact_number"))["irt_guessing"] == 0.0

    def test_discrimination_is_set_not_left_to_schema_default(self):
        assert row(task())["irt_discrimination"] > 0

    def test_upsert_sql_carries_all_three(self):
        for column in ("irt_discrimination", "irt_difficulty", "irt_guessing"):
            assert f":{column}" in S._UPSERT_SQL, f"{column} не уезжает в staging"
            assert f":{column}" in S._INSERT_MASTER_SQL, f"{column} не уезжает в master"


class TestMasterIrt:
    def test_stored_value_wins(self):
        params = S._master_irt({
            "irt_discrimination": 1.0, "irt_difficulty": 1.5, "irt_guessing": 0.2,
            "difficulty": "A", "answer_type": "exact_number",
        })
        # Считать заново из difficulty нельзя: человек в карантине видел 1.5.
        assert params["irt_difficulty"] == 1.5

    def test_legacy_row_without_columns_is_recomputed(self):
        # Строка, записанная до миграции: колонок нет. Дефолт схемы (0.0)
        # уехал бы всем подряд — то есть ровно B39.
        params = S._master_irt({"difficulty": "C", "answer_type": "multiple_choice"})
        assert params["irt_difficulty"] == 1.5
        assert params["irt_guessing"] > 0

    def test_migration_default_zero_is_recomputed(self):
        # Настоящий легаси-случай, а не «колонок нет»: `ADD COLUMN ... DEFAULT
        # 0.0` заполняет существующие строки нулём, и они читаются как 0.0, а
        # не как NULL. На живой базе так выглядел **каждый** из 421 кандидата
        # на промоушен.
        params = S._master_irt({
            "irt_discrimination": 1.0, "irt_difficulty": 0.0, "irt_guessing": 0.0,
            "difficulty": "C", "answer_type": "multiple_choice",
        })
        assert params["irt_difficulty"] == 1.5
        assert params["irt_guessing"] > 0

    def test_zero_from_decimal_is_recomputed(self):
        # NUMERIC(6,4) приезжает из драйвера как Decimal, а не float.
        from decimal import Decimal
        params = S._master_irt({
            "irt_discrimination": Decimal("1.0"),
            "irt_difficulty": Decimal("0.0000"),
            "irt_guessing": Decimal("0.0000"),
            "difficulty": "A", "answer_type": "exact_number",
        })
        assert params["irt_difficulty"] == -1.0

    def test_no_difficulty_maps_to_zero_after_recompute(self):
        # Формула не должна возвращать ноль ни для одной сложности — иначе
        # правило «ноль значит не посчитано» перестаёт быть различающим.
        from src.pipeline import schema_vocab as vocab
        got = {vocab.irt_params(d, "exact_number")["irt_difficulty"] for d in "ABC"}
        assert 0.0 not in got


# ---------------------------------------------------------------------------
# B41 — verification_status
# ---------------------------------------------------------------------------


class TestVerificationStatus:
    def test_gate_pass_alone_is_not_verified(self):
        # Гейт проверяет структуру, провенанс, артефакты и компиляцию формул,
        # но НЕ математику. «Проверено» тут означало бы, что ответ проверял
        # кто-то, кого не было.
        assert S.verification_status({}) == "pending"

    def test_smart_verify_success_is_verified(self):
        assert S.verification_status({"smart_verify_status": "verified_match"}) == "verified"

    def test_smart_verify_failure_is_not_verified(self):
        assert S.verification_status({"smart_verify_status": "failed_at_llm"}) == "pending"

    def test_sympy_verified_is_verified(self):
        # Признак, по которому судил `db_writer`.
        assert S.verification_status({"sympy_verified": True}) == "verified"

    def test_missing_tags_are_not_verified(self):
        assert S.verification_status(None) == "pending"

    def test_master_insert_no_longer_hardcodes_verified(self):
        assert "'verified'" not in S._INSERT_MASTER_SQL
        assert ":verification_status" in S._INSERT_MASTER_SQL


class TestQualityTags:
    def test_sympy_flag_survives_the_write(self):
        # `db_writer` дописывал тег перед записью; `_row` отдавал tags как есть,
        # и признак для поиска расхождения постфактум не сохранялся.
        tags = S.quality_tags(task(sympy_verified=True, sympy_confidence=0.912))
        assert tags["sympy_verified"] is True
        assert tags["sympy_confidence"] == 0.912

    def test_unverified_task_is_marked_explicitly(self):
        assert S.quality_tags(task())["sympy_verified"] is False

    def test_existing_tags_are_kept(self):
        tags = S.quality_tags(task(tags={"smart_verify_status": "verified_match"}))
        assert tags["smart_verify_status"] == "verified_match"

    def test_task_tags_are_not_mutated(self):
        t = task(tags={"a": 1})
        S.quality_tags(t)
        assert t.tags == {"a": 1}

    def test_promoted_status_follows_the_tags_written_to_staging(self):
        verified = S.verification_status(S.quality_tags(task(sympy_verified=True)))
        plain = S.verification_status(S.quality_tags(task()))
        assert (verified, plain) == ("verified", "pending")


# ---------------------------------------------------------------------------
# B44 — разведение дублей id внутри батча
# ---------------------------------------------------------------------------


class TestDedupeTaskId:
    def test_free_id_is_returned_as_is(self):
        assert S.dedupe_task_id("G8_TB_1_1", set()) == "G8_TB_1_1"

    def test_short_ids_get_readable_suffixes(self):
        used = {"G8_TB_1_1"}
        second = S.dedupe_task_id("G8_TB_1_1", used)
        used.add(second)
        third = S.dedupe_task_id("G8_TB_1_1", used)
        assert (second, third) == ("G8_TB_1_1_dup2", "G8_TB_1_1_dup3")

    @pytest.mark.parametrize("length", [60, 57, 59])
    def test_long_id_terminates(self, length):
        """Было: обрезка до 60 съедала суффикс, кандидат переставал меняться.

        Цикл крутился вечно внутри открытой транзакции `engine.begin()`, то
        есть вешал и прогон, и транзакцию. Воспроизводилось на 60 и 57.
        """
        base = "G" * length
        used = {base}
        for _ in range(5):
            got = S.dedupe_task_id(base, used)
            assert got not in used
            assert len(got) <= S.TASK_ID_MAXLEN
            used.add(got)

    def test_suffix_replaces_the_tail_not_overflows_it(self):
        base = "G" * S.TASK_ID_MAXLEN
        got = S.dedupe_task_id(base, {base})
        assert got.endswith("_dup2")
        assert len(got) == S.TASK_ID_MAXLEN

    def test_pathological_batch_falls_back_to_unique_id(self):
        # 1000 различных дублей одного номера — сломана сегментация, а не
        # повод искать ещё один суффикс. Но и потерять задачу нельзя.
        base = "G" * S.TASK_ID_MAXLEN
        used = {base}
        used.update(
            base[: S.TASK_ID_MAXLEN - len(f"_dup{n}")] + f"_dup{n}"
            for n in range(2, 1000)
        )
        got = S.dedupe_task_id(base, used)
        assert got not in used and len(got) <= S.TASK_ID_MAXLEN
