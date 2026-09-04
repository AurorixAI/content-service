"""Формат идентификаторов задач — сверен с выгрузкой прода от 2026-09-01."""
from src.pipeline.task_ids import (
    MAX_TASK_ID_LEN,
    build_source_reference,
    build_task_id,
    normalize_id_part,
    transliterate,
)


class TestNormalizeIdPart:
    def test_dot_becomes_underscore(self):
        # Правило существующего писателя: `G10_TB_§22_22_5_1` в проде.
        assert normalize_id_part("22.5.1") == "22_5_1"

    def test_paragraph_sign_dropped(self):
        assert normalize_id_part("§22") == "22"

    def test_number_sign_dropped(self):
        assert normalize_id_part("№14") == "14"

    def test_en_dash_becomes_hyphen(self):
        # `G6_TB_40–42_353` — длинное тире в 2 192 идентификаторах прода.
        assert normalize_id_part("40–42") == "40-42"

    def test_all_dash_variants_normalised(self):
        assert {normalize_id_part(f"1{d}2") for d in "‐‑‒–—―−"} == {"1-2"}

    def test_spaces_removed(self):
        assert normalize_id_part("Тест X") == "TestX"

    def test_cyrillic_subtask_letter(self):
        assert normalize_id_part("42.а") == "42_a"

    def test_cyrillic_word(self):
        # `G9_TB_УКГ4_429_2` — иначе часть параграфа исчезает целиком.
        assert normalize_id_part("УКГ4") == "UKG4"

    def test_result_is_ascii(self):
        for raw in ("§1.4", "40–42", "УКГ4", "Тест X", "14.10.а"):
            assert normalize_id_part(raw).isascii()

    def test_empty_input(self):
        assert normalize_id_part("") == ""
        assert normalize_id_part(None) == ""

    def test_repeated_separators_collapse(self):
        assert normalize_id_part("1..2") == "1_2"

    def test_no_trailing_separator(self):
        assert normalize_id_part("12.") == "12"


class TestTransliterate:
    def test_case_preserved(self):
        assert transliterate("Ася") == "Asya"

    def test_latin_untouched(self):
        assert transliterate("abc123") == "abc123"

    def test_soft_sign_disappears_without_trace(self):
        assert transliterate("соль") == "sol"


class TestBuildTaskId:
    def test_prod_shape(self):
        assert build_task_id("G5_TB", "10", "161") == "G5_TB_10_161"

    def test_subtask_letter_transliterated(self):
        assert build_task_id("G5_TB", "1.1", "42.а") == "G5_TB_1_1_42_a"

    def test_missing_paragraph_leaves_no_double_underscore(self):
        assert build_task_id("G5_TB", "", "486") == "G5_TB_486"

    def test_missing_both_parts_returns_empty(self):
        # Пустая строка — сигнал вызывающему. Вернуть один «G5_TB» на все
        # задачи нельзя: при записи они склеятся в одну строку.
        assert build_task_id("G5_TB", "", "") == ""

    def test_truncated_to_column_width(self):
        long = build_task_id("G5_TB", "1" * 40, "2" * 40)
        assert len(long) <= MAX_TASK_ID_LEN

    def test_truncation_leaves_no_trailing_separator(self):
        assert not build_task_id("G5_TB", "1" * 54, "2.3").endswith("_")

    def test_cyrillic_and_latin_subtasks_no_longer_diverge(self):
        # В проде 1 513 идентификаторов с кириллическим подпунктом и 1 184 с
        # латинским — один и тот же подпункт книги в двух написаниях.
        assert build_task_id("G5_TB", "5", "85.а") == build_task_id("G5_TB", "5", "85.a")


class TestBuildSourceReference:
    def test_prod_format(self):
        assert (
            build_source_reference("0fd78e9c-1688-43fa-aea0-bf3a16030034", "1.1", "1.1")
            == "0fd78e9c-1688-43fa-aea0-bf3a16030034::1.1:1.1"
        )

    def test_book_text_kept_verbatim(self):
        # Это ссылка для человека: «14.10.а» должно читаться как в книге.
        assert build_source_reference("uuid", "1.4", "14.10.а").endswith("::1.4:14.10.а")

    def test_no_textbook_means_no_reference(self):
        assert build_source_reference("", "1.1", "1") == ""
