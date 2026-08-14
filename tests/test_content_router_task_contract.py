from src.api.content_router import _task_row_full


def test_content_task_api_keeps_canonical_and_display_option_layers_parallel():
    row = (
        "task-1", "skill-1", "Навык", "B", "Условие", "Условие $x$",
        "mcq", "2", "$2$", ["2", "1"], ["$2$", "$1$"], [{"value": "1"}],
        1.2, -0.3, 0.25, "rejected", "verified", False,
        {"status": "mathematically_invalid"},
    )

    task = _task_row_full(row)

    assert task["answer_options"] == ["2", "1"]
    assert task["answer_options_latex"] == ["$2$", "$1$"]
    assert task["distractor_meta"] == [{"value": "1"}]
    assert task["irt_discrimination"] == 1.2
    assert task["verification_status"] == "rejected"
    assert task["latex_status"] == "verified"
    assert task["is_active"] is False
    assert task["content_quality"] == {"status": "mathematically_invalid"}
