"""Regression tests for safe figure-to-task attachment."""

from src.pipeline.figure_links import attach_figure_refs
from src.pipeline.figures import figure_id_for
from src.pipeline.models import ExtractedTask


def _task(**overrides) -> ExtractedTask:
    defaults = {
        "temp_id": "task-1",
        "paragraph_number": "§ 2",
        "exercise_number": "11.2",
        "question_text": "На рис. 2.12 изображён график функции.",
        "answer_raw": "",
    }
    defaults.update(overrides)
    return ExtractedTask(**defaults)


def test_preserves_explicit_reference_from_extractor():
    task = _task(figure_refs=["fig-book-p31-1"])

    result = attach_figure_refs(
        [task],
        '10. [FIGURE id="fig-book-p30-1"]\n11. задача',
        {"fig-book-p30-1": object(), "fig-book-p31-1": object()},
    )

    assert result[0].figure_refs == ["fig-book-p31-1"]


def test_attaches_only_marker_in_exact_exercise_block():
    task = _task(exercise_number="11")

    result = attach_figure_refs(
        [task],
        '10. Задача по рис. 2.11 [FIGURE id="fig-book-p30-1"]\n'
        '11. Задача по рис. 2.12 [FIGURE id="fig-book-p31-1"]',
        {"fig-book-p30-1": object(), "fig-book-p31-1": object()},
    )

    assert result[0].figure_refs == ["fig-book-p31-1"]


def test_does_not_borrow_figure_from_another_exercise_or_paragraph():
    task = _task(exercise_number="11")

    result = attach_figure_refs(
        [task],
        '10. Задача по рис. 2.11 [FIGURE id="fig-book-p30-1"]\n'
        '11. На рис. 2.12 изображён график, но его маркер не найден.',
        {"fig-book-p30-1": object()},
    )

    assert result[0].figure_refs == []
    assert not result[0].requires_figure


def test_figure_ids_are_unique_between_textbooks():
    assert figure_id_for("aaaaaaaa-1111-2222-3333-444444444444", 30, 1) != figure_id_for(
        "bbbbbbbb-1111-2222-3333-444444444444", 30, 1
    )
