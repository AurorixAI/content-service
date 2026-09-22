"""Safety tests: LaTeX backfill must never mutate educational source data."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import asyncio

import pytest
import requests

from src.pipeline import deepseek_client


_SCRIPT = Path(__file__).parents[1] / "scripts" / "backfill_latex_deepseek.py"
_SPEC = importlib.util.spec_from_file_location("backfill_latex_deepseek", _SCRIPT)
assert _SPEC and _SPEC.loader
backfill = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(backfill)


class _Connection:
    def __init__(self, current_row):
        self.current_row = current_row
        self.writes = []

    def execute(self, statement, parameters=None):
        if "SELECT question_text" in str(statement):
            if len(self.current_row) == 8:
                current = self.current_row
            else:
                q, a, dmeta, *options = self.current_row
                current = (q, a, dmeta, options[0] if options else [], "", "", None, None)
            return type("Result", (), {"fetchone": lambda _self: current})()
        self.writes.append((str(statement), parameters))
        return None


def _accepted(value: str) -> dict:
    return {
        "canonical": value,
        "decision": "REPLACE",
        "confidence": "high",
        "ambiguity_reason": None,
        "katex_ok": True,
        "katex_error": "",
        "contract_ok": True,
        "contract_error": "",
        "professional_ok": True,
        "professional_error": "",
        "semantic_ok": True,
        "semantic_error": "",
    }


def test_semantic_gate_accepts_nested_fraction_and_greek_latex_projection():
    ok, reason = backfill.semantic_preservation_check(
        "Найдите α = 15/8 + 2/3",
        r"Найдите $\alpha = \dfrac{15}{8} + \dfrac{2}{3}$",
    )

    assert ok is True
    assert reason == ""


def test_semantic_gate_accepts_only_presentation_change_in_existing_formula():
    ok, reason = backfill.semantic_preservation_check(
        r"Решите $x = \frac{1}{2}$.",
        r"Решите $x = \dfrac{1}{2}$.",
    )

    assert ok is True
    assert reason == ""


def test_semantic_gate_accepts_bare_latex_distractor_normalization():
    ok, reason = backfill.semantic_preservation_check(
        r"-\frac{5}{4}",
        r"$-\dfrac{5}{4}$",
    )

    assert ok is True
    assert reason == ""


def test_semantic_gate_accepts_legacy_thousands_separator_repair():
    ok, reason = backfill.semantic_preservation_check(
        r"Население $2\$,$847\$,$391$ человек.",
        r"Население $2\,847\,391$ человек.",
        allow_legacy_markup_repair=True,
    )

    assert ok is True
    assert reason == ""


def test_semantic_gate_accepts_merged_implication_variable_repair():
    ok, reason = backfill.semantic_preservation_check(
        r"$x^{2}>0\Rightarrowx\in(-\infty;2)$",
        r"$x^{2} > 0 \Rightarrow x \in (-\infty; 2)$",
        allow_legacy_markup_repair=True,
    )

    assert ok is True
    assert reason == ""


def test_decimal_gate_does_not_reject_a_separate_list_near_another_decimal():
    source = "Вероятности: $0$.$2$, $0$.$3$; значения: $0$, $1$."
    rendered = "Вероятности: $0{,}2$, $0{,}3$; значения: $0$, $1$."

    assert backfill.validate_display_contract("question", source, rendered) == (True, "")


def test_pure_math_gate_does_not_wrap_english_prose_as_formula():
    assert backfill._is_pure_math_value("answer", "x = 2; example: 2, 4, 8") is False


def test_semantic_gate_accepts_latex_ellipsis_for_plain_ellipsis():
    assert backfill.semantic_preservation_check(
        "example: 2, 4, 8, ...", "example: $2, 4, 8, \\dots$",
        allow_legacy_markup_repair=True,
    ) == (True, "")


def test_pure_math_value_contract_rejects_multiple_inline_blocks():
    ok, reason = backfill.validate_display_contract(
        "answer",
        r"$x = \dfrac{8}{25}; y = \dfrac{-43}{50}$",
        r"$x = \dfrac{8}{25}$; $y = \dfrac{-43}{50}$",
    )

    assert ok is False
    assert reason == "pure_math_value_must_be_one_inline_formula"


def test_professional_gate_rejects_legacy_array_system():
    ok, reason = backfill.validate_professional_latex(
        r"$$\left\{\begin{array}{l}x=1\\y=2\end{array}\right.$$"
    )

    assert ok is False
    assert reason == "professional_style_requires_cases_for_system"


@pytest.mark.parametrize(
    "value",
    [
        r"Решите $\begin{cases}x=1\\y=2\end{cases}$.",
        r"Вычислите $\int_{0}^{1} x\,dx$.",
        r"Найдите $\lim_{x\to0} x$.",
    ],
)
def test_professional_gate_requires_display_math_for_large_constructs(value):
    ok, reason = backfill.validate_display_contract("question", value, value)

    assert ok is False
    assert reason in {
        "professional_style_requires_display_system",
        "professional_style_requires_display_operator",
    }


def test_professional_gate_accepts_display_cases_and_integral():
    value = (
        "Решите:\n$$\\begin{cases}x=1\\\\y=2\\end{cases}$$\n"
        "и вычислите:\n$$\\int_{0}^{1} x\\,dx$$"
    )
    ok, reason = backfill.validate_display_contract("question", value, value)

    assert ok is True
    assert reason == ""


@pytest.mark.parametrize("label", ["answer", "dmeta[0].value", "option[3]"])
def test_pure_answer_value_accepts_one_inline_large_operator(label):
    value = r"$\int_{0}^{1} x\,dx$"

    contract_ok, contract_reason = backfill.validate_display_contract(label, value, value)
    style_ok, style_reason = backfill.validate_professional_latex(value)

    assert contract_ok is True
    assert contract_reason == ""
    assert style_ok is True
    assert style_reason == ""


@pytest.mark.parametrize(
    "value",
    [r"$S=b_{1}/(1-q)$", r"$n \cdot (n-1) / 2$", r"$/$"],
)
def test_professional_gate_rejects_every_arithmetic_bare_slash(value):
    ok, reason = backfill.validate_professional_latex(value)

    assert ok is False
    assert reason == "professional_style_requires_dfrac"


@pytest.mark.parametrize(
    "value",
    [r"$7{,}5\,\text{л/см}$", r"$80$ км/ч и $60$ км/ч"],
)
def test_professional_gate_allows_unit_slash_as_text(value):
    ok, reason = backfill.validate_professional_latex(value)

    assert ok is True
    assert reason == ""


def test_stale_verified_prefilter_covers_every_required_display_layer():
    assert backfill.stored_task_has_non_katex_gate_issue(
        "Решите систему", r"Решите $$\begin{cases}x=1\\y=2\end{cases}$$",
        r"$x=1; y=2$", r"$x=1$; $y=2$",
        [{
            "value": r"$x=0$", "value_latex": r"$x=0$",
            "error_logic": "Ошибка", "error_logic_latex": "Ошибка",
        }],
        [r"$x=1; y=2$"], [r"$x=1; y=2$"],
    ) is True

    professional_question = "Решите:\n$$\\begin{cases}x=1\\\\y=2\\end{cases}$$"
    assert backfill.stored_task_has_non_katex_gate_issue(
        professional_question, professional_question,
        r"$x=1; y=2$", r"$x=1; y=2$",
        [{
            "value": r"$x=0$", "value_latex": r"$x=0$",
            "error_logic": "Ошибка", "error_logic_latex": "Ошибка",
        }],
        [r"$x=1; y=2$"], [r"$x=1; y=2$"],
    ) is False


def test_stale_verified_prefilter_detects_option_and_description_issues():
    base = ("Q", "Q", "A", "A")
    assert backfill.stored_task_has_non_katex_gate_issue(
        *base,
        [{"value": "1", "value_latex": "$1$", "error_logic": r"$\int x dx$", "error_logic_latex": r"$\int x\,dx$"}],
        [], [],
    ) is True
    assert backfill.stored_task_has_non_katex_gate_issue(
        *base, [], [r"$x=1; y=2$"], [r"$x=1$; $y=2$"],
    ) is True


def test_final_display_contract_requires_every_layer_before_verified(monkeypatch):
    monkeypatch.setattr(backfill, "validate_with_katex", lambda _value: (True, ""))
    monkeypatch.setattr(backfill, "validate_display_contract", lambda *_args: (True, ""))
    monkeypatch.setattr(backfill, "validate_professional_latex", lambda _value: (True, ""))
    monkeypatch.setattr(backfill, "semantic_preservation_check", lambda *_args, **_kwargs: (True, ""))

    clean = backfill.final_display_issues(
        "Условие", "Условие", "$2$", "$2$",
        [{"value": "$1$", "value_latex": "$1$", "error_logic": "Ошибка", "error_logic_latex": "Ошибка"}],
        ["$2$", "$1$"], ["$2$", "$1$"],
    )
    assert clean[0] == {}
    assert backfill.latex_status_from_issues(*clean) == "verified"

    issues, required = backfill.final_display_issues(
        "Условие", "Условие", "$2$", "$2$",
        [{"value": "$1$", "value_latex": "", "error_logic": "Ошибка", "error_logic_latex": "Ошибка"}],
        ["$2$"], ["$2$"],
    )
    assert issues == {"dmeta[0].value": {"reason": "missing_display_value", "confidence": "low"}}
    assert backfill.latex_status_from_issues(issues, required) == "partial"


def test_empty_stale_verified_exact_set_cannot_fall_back_to_regular_queue():
    assert backfill.build_task_filter([], exact_set_mode=True) == "AND FALSE"
    assert backfill.build_task_filter([], exact_set_mode=False) == ""
    assert backfill.build_task_filter(["task-1"], exact_set_mode=True) == (
        "AND tm.id = ANY(:task_ids)"
    )


@pytest.mark.parametrize(
    ("source", "display", "reason"),
    [
        (r"Вычислите $x^2 - 6$.", r"Вычислите $x^{2-6}$.", "semantic_existing_math_fragment_changed"),
        (r"Решите $x = 2$.", r"Найдите $x = 2$.", "semantic_text_sequence_changed"),
        (r"Решите $x = 2$.", r"Решите $x = 2$ и $y = 3$.", "semantic_number_sequence_changed"),
    ],
)
def test_semantic_gate_rejects_existing_math_or_prose_rewrite(source, display, reason):
    ok, actual_reason = backfill.semantic_preservation_check(source, display)

    assert ok is False
    assert actual_reason == reason


def test_semantic_gate_accepts_new_delimiters_around_plain_math_after_existing_formula():
    ok, reason = backfill.semantic_preservation_check(
        r"Проверьте $x = 2$, затем 25-15=10.",
        r"Проверьте $x = 2$, затем $(25-15=10)$.",
    )

    assert ok is True
    assert reason == ""


def test_llm_normalization_of_existing_formula_is_accepted(monkeypatch):
    monkeypatch.setattr(
        backfill,
        "call_deepseek_latex",
        lambda _prompt: "@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\nРешите $x = \\dfrac{1}{2}$.\n@@END",
    )

    result = asyncio.run(backfill.format_latex(
        r"Решите $x = \frac{1}{2}$.", asyncio.Semaphore(1)
    ))

    assert result["canonical"] == r"Решите $x = \dfrac{1}{2}$."
    assert result["confidence"] == "high"
    assert result["katex_ok"] is True


def test_repair_invalid_mode_resubmits_only_the_invalid_display_field(monkeypatch):
    monkeypatch.setattr(
        backfill,
        "call_deepseek_task_bundle",
        lambda _prompt: "@@FIELD: question\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\nРешите $x^{2}$.\n@@END_FIELD",
    )

    async def process() -> dict:
        return await backfill.process_task(
            "task-1",
            r"Решите $x^2$.",
            r"Решите $x^{$x^2$}$.",
            "2",
            "$2$",
            [],
            [],
            [],
            asyncio.Semaphore(1),
            repair_invalid=True,
        )

    result = asyncio.run(process())

    assert set(result["field_results"]) == {"question"}
    assert result["field_results"]["question"]["canonical"] == r"Решите $x^{2}$."


def test_each_display_field_gets_an_independent_request_with_full_task_context(monkeypatch):
    prompts = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        assert "@@FIELD_CONTEXT: question" in prompt
        assert "@@FIELD_CONTEXT: answer" in prompt
        output_line = next(
            line for line in prompt.splitlines() if line.startswith("@@OUTPUT_FIELDS:")
        )
        label = output_line.partition(":")[2].strip()
        assert "," not in label
        rendered = {"question": "Найдите $x$", "answer": "$2$"}[label]
        return (
            f"@@FIELD: {label}\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
            f"@@REASON: NONE\n@@TEXT:\n{rendered}\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)
    async def run_bundle():
        return await backfill.format_task_bundle(
            {"question": "Найдите x", "answer": "2"},
            {"question": "", "answer": ""},
            {
                "question": {"raw": "Найдите x", "current": ""},
                "answer": {"raw": "2", "current": ""},
            },
            asyncio.Semaphore(2),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert len(prompts) == 4
    assert sum("@@SECOND_PASS_INDEPENDENT_REVIEW:" in prompt for prompt in prompts) == 2
    assert set(results) == {"question", "answer"}
    assert all(result["llm_self_check_used"] is True for result in results.values())
    assert all(result["llm_self_review_ok"] is True for result in results.values())
    assert all(backfill.field_is_acceptable(result) for result in results.values())


def test_invalid_field_remains_for_review_after_bounded_llm_repair_attempts(monkeypatch):
    prompts = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        rendered = r"$3/4$"
        return (
            "@@FIELD: answer\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
            f"@@REASON: NONE\n@@TEXT:\n{rendered}\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)
    async def run_bundle():
        return await backfill.format_task_bundle(
            {"question": "Вычислите", "answer": "3/4"},
            {"question": "Вычислите", "answer": ""},
            {"answer": {"raw": "3/4", "current": ""}},
            asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert len(prompts) == 3
    # A technical-only retry deliberately uses a compact, single-field prompt:
    # the small formatter model is more reliable without the multi-field
    # protocol.  It may return only the repaired display string.
    assert "Верни только готовый русский display-текст" in prompts[1]
    assert "SOURCE:\n3/4" in prompts[1]
    assert "@@FIELD:" not in prompts[1]
    assert "Верни только готовый русский display-текст" in prompts[2]
    assert results["answer"]["canonical"] == r"$3/4$"
    assert results["answer"]["llm_self_check_used"] is False
    assert results["answer"]["llm_self_review_ok"] is False
    assert results["answer"]["final_review"]["verdict"] == "repair_attempts_exhausted"
    assert backfill.field_is_acceptable(results["answer"]) is False


def test_second_model_review_is_the_contextual_authority_for_legacy_normalisation(monkeypatch):
    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        rendered = r"Решите $x$." if len(calls) == 1 else r"Решите $y$."
        return (
            "@@FIELD: question\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
            f"@@REASON: NONE\n@@TEXT:\n{rendered}\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)

    async def run_bundle():
        return await backfill.format_task_bundle(
            {"question": "Решите x."}, {"question": ""},
            {"question": {"raw": "Решите x.", "current": ""}},
            asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert len(calls) == 2
    assert results["question"]["llm_self_review_ok"] is True
    assert results["question"]["semantic_ok"] is False
    # The deterministic comparison remains diagnostic only: legacy/OCR source
    # may require contextual normalisation. The required second model pass is
    # the final authoring decision, while syntax, layout and house-style still
    # have to pass independently.
    assert backfill.field_is_acceptable(results["question"]) is True


def test_boundary_defect_remains_for_review_after_bounded_llm_repair_attempts(monkeypatch):
    prompts = []

    def llm(prompt: str) -> str:
        prompts.append(prompt)
        rendered = r"Ошибка: $(6+10$ или $6+11-1)$"
        return (
            "@@FIELD: dmeta[0].description\n@@DECISION: REPLACE\n"
            "@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\n"
            f"{rendered}\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)
    raw = r"Ошибка: $(6+10$ или $6+11-1)$"
    async def run_bundle():
        return await backfill.format_task_bundle(
            {"dmeta[0].description": raw},
            {"dmeta[0].description": raw},
            {"dmeta[0].description": {"raw": raw, "current": raw}},
            asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert len(prompts) == 3
    assert "Верни только готовый русский display-текст" in prompts[1]
    assert "SOURCE:\nОшибка: (6+10 или 6+11-1)" in prompts[1]
    assert "@@FIELD:" not in prompts[1]
    assert "Верни только готовый русский display-текст" in prompts[2]
    assert results["dmeta[0].description"]["canonical"] == (
        r"Ошибка: $(6+10$ или $6+11-1)$"
    )
    assert backfill.field_is_acceptable(results["dmeta[0].description"]) is False


def test_llm_keep_decision_preserves_existing_display_verbatim(monkeypatch):
    def llm(prompt: str) -> str:
        assert "@@RAW:\nНайдите x" in prompt
        assert "@@CURRENT_LATEX:\nНайдите $x$" in prompt
        return "@@FIELD: question\n@@DECISION: KEEP\n@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\nНайдите $x$\n@@END_FIELD"

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)

    async def process() -> dict:
        return await backfill.process_task(
            "task-1", "Найдите x", "Найдите $x$", "2", "$2$", [], [], [],
            asyncio.Semaphore(1), force_reformat=True,
        )

    result = asyncio.run(process())

    field = result["field_results"]["question"]
    assert field["decision"] == "KEEP"
    assert field["canonical"] == "Найдите $x$"
    assert backfill.field_is_acceptable(field) is True


def test_llm_keep_decision_cannot_change_existing_display(monkeypatch):
    monkeypatch.setattr(
        backfill,
        "call_deepseek_task_bundle",
        lambda _prompt: "@@FIELD: question\n@@DECISION: KEEP\n@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\nНайдите $y$\n@@END_FIELD",
    )

    async def process() -> dict:
        return await backfill.process_task(
            "task-1", "Найдите x", "Найдите $x$", "2", "$2$", [], [], [],
            asyncio.Semaphore(1), force_reformat=True,
        )

    result = asyncio.run(process())

    field = result["field_results"]["question"]
    assert backfill.field_is_acceptable(field) is False
    assert field["contract_error"] == "keep_value_changed"


def test_task_bundle_parser_keeps_reason_separate_from_confidence():
    parsed = backfill.parse_task_bundle_response(
        "@@FIELD: question\n@@DECISION: REVIEW\n@@CONFIDENCE: high\n@@REASON: malformed legacy delimiter\n@@TEXT:\nQ\n@@END_FIELD",
        {"question": {"raw": "Q", "current": "Q"}},
    )

    assert parsed["question"]["confidence"] == "high"
    assert parsed["question"]["ambiguity_reason"] == "malformed legacy delimiter"


def test_focused_single_field_parser_treats_plain_model_text_as_unapproved_draft():
    parsed = backfill.parse_task_bundle_response(
        "Получено ($10$ л).",
        {"question": {"raw": "Получено (10 л).", "current": ""}},
        allow_bare_single_field=True,
    )

    assert parsed["question"] == {
        "canonical": "Получено ($10$ л).",
        "decision": "REPLACE",
        "confidence": "low",
        "ambiguity_reason": None,
        "requires_explicit_final_review": True,
        "response_protocol": "bare_repair_draft",
    }
    rejected = backfill.parse_task_bundle_response(
        "@@TEXT:\nПолучено ($10$ л).",
        {"question": {"raw": "Получено (10 л).", "current": ""}},
        allow_bare_single_field=True,
    )
    assert rejected["question"]["decision"] == "REVIEW"


def test_replace_can_repair_legacy_delimiters_without_changing_content():
    source = "Вычислите $(25-15=10$ чисел)."
    display = "Вычислите $(25-15=10)$ чисел."

    strict_ok, _ = backfill.semantic_preservation_check(source, display)
    repair_ok, reason = backfill.semantic_preservation_check(
        source, display, allow_legacy_markup_repair=True,
    )

    assert strict_ok is False
    assert repair_ok is True
    assert reason == ""




def test_katex_validator_rejects_an_unmatched_math_delimiter():
    valid, error = backfill.validate_with_katex("Решите $x + 1")

    assert valid is False
    assert "unmatched_math_delimiter" in error


def test_value_display_contract_requires_latex_delimiters():
    assert backfill.validate_display_contract("dmeta[0].value", "27", "27") == (
        False, "pure_math_value_must_be_one_inline_formula",
    )
    assert backfill.validate_display_contract("option[3]", "27", "$27$") == (True, "")
    assert backfill.validate_display_contract("answer", "-5/4", "$-\\dfrac{5}{4}$") == (True, "")
    assert backfill.validate_display_contract(
        "answer",
        "$1) x=-5; 2) x=4$",
        "1) $x=-5$; 2) $x=4$",
    ) == (True, "")
    assert backfill.validate_display_contract(
        "dmeta[0].value", "Функция возрастает", "Функция возрастает",
    ) == (True, "")
    assert backfill.validate_display_contract(
        "dmeta[0].description", "Текст без формулы", "Текст без формулы",
    ) == (True, "")


def test_display_contract_rejects_bare_latex_command():
    assert backfill.validate_display_contract(
        "question", r"Вычислите \frac{1}{2}", r"Вычислите \dfrac{1}{2}",
    ) == (False, "latex_command_outside_math_delimiters")


@pytest.mark.parametrize(
    "display",
    [
        "Вычисли $(25-15=10$ чисел)",
        "(или ошибка: $451$ вместо $441)$",
    ],
)
def test_display_contract_rejects_parentheses_crossing_math_boundaries(display):
    assert backfill.validate_display_contract("question", display, display) == (
        False, "parenthesis_crosses_math_boundary",
    )


def test_display_contract_cannot_close_parenthesis_in_a_later_math_fragment():
    display = "Получено $(0x=18$; затем $4a+6)$ — неверно."

    assert backfill.validate_display_contract("question", display, display) == (
        False, "parenthesis_crosses_math_boundary",
    )


def test_display_contract_rejects_legacy_split_decimal_math_boundaries():
    source = r"Вычислите $5$, $2 \cdot 0$, $4$"
    repaired = r"Вычислите $5{,}2 \cdot 0{,}4$"

    assert backfill.validate_display_contract("question", source, source) == (
        False, "legacy_split_decimal_math_boundary",
    )
    assert backfill.validate_display_contract("question", source, repaired) == (True, "")
    assert backfill.semantic_preservation_check(
        source, repaired, allow_legacy_markup_repair=True,
    ) == (True, "")


def test_display_contract_allows_separate_math_fragments_for_a_non_decimal_list():
    source = "При подстановке получили 8, 2^2 = 4."
    rendered = r"При подстановке получили $8$, $2^{2} = 4$."

    assert backfill.validate_display_contract("dmeta[0].description", source, rendered) == (True, "")


def test_display_contract_rejects_split_rendering_of_a_clean_raw_decimal():
    source = "Получили 5,2."
    rendered = "Получили $5$, $2$."

    assert backfill.validate_display_contract("dmeta[0].description", source, rendered) == (
        False, "legacy_split_decimal_math_boundary",
    )


def test_semantic_check_accepts_ascii_arrow_normalised_to_latex_arrow():
    source = "Получили x^2 = 1 -> x = 1."
    rendered = r"Получили $x^{2} = 1 \rightarrow x = 1$."

    assert backfill.semantic_preservation_check(
        source, rendered, allow_legacy_markup_repair=True,
    ) == (True, "")


def test_decimal_gate_does_not_cross_a_complete_decimal_and_next_list_item():
    source = r"Вероятность $0{$,$}1$, $1$ случай."
    rendered = r"Вероятность $0{,}1$, $1$ случай."

    assert backfill.validate_display_contract("question", source, rendered) == (True, "")


def test_display_contract_rejects_punctuation_wrapped_as_math():
    source = "Ответ запишите в виде дроби $.$"
    repaired = "Ответ запишите в виде дроби."

    assert backfill.validate_display_contract("question", source, source) == (
        False, "legacy_punctuation_only_math_fragment",
    )
    assert backfill.validate_display_contract("question", source, repaired) == (True, "")
    assert backfill.semantic_preservation_check(
        source, repaired, allow_legacy_markup_repair=True,
    ) == (True, "")


def test_stale_verified_prefilter_detects_missing_dmeta_description_latex():
    assert backfill.stored_task_has_non_katex_gate_issue(
        "Q", "Q", "A", "$A$",
        [{"value": "1", "value_latex": "$1$", "error_logic": "Ошибка с 2"}],
        [], [],
    ) is True


def test_math_boundary_diagnostics_identifies_each_broken_fragment():
    diagnostics = backfill._math_boundary_diagnostics(
        "Получено $(0x=18$; затем $4a+6)$ — неверно."
    )

    assert any("math_fragment[0] unmatched_opening_(" in item for item in diagnostics)
    assert any("math_fragment[1] unmatched_closing_)" in item for item in diagnostics)


def test_display_contract_accepts_parentheses_on_consistent_side_of_delimiters():
    assert backfill.validate_display_contract(
        "question", "Вычисли (25-15=10 чисел)", "Вычисли $(25-15=10)$ чисел",
    ) == (True, "")
    assert backfill.validate_display_contract(
        "question", "(или ошибка: 451 вместо 441)", "(или ошибка: $451$ вместо $441$)",
    ) == (True, "")
    assert backfill.validate_display_contract(
        "answer", "x∈(-∞;5]", "$x \\in (-\\infty; 5]$",
    ) == (True, "")
    assert backfill.validate_display_contract(
        "question",
        "Найдите: а) точки; б) интервалы.",
        "Найдите: а) точки; б) интервалы.",
    ) == (True, "")


def test_display_contract_accepts_enumeration_after_a_completed_sentence():
    display = (
        "Даны функции $f(x)=x^{2}$ и $g(x)=x-3$. "
        "a) найдите $f(g(x))$; b) найдите $g(f(x))$."
    )

    assert backfill.validate_display_contract("question", display, display) == (True, "")


def test_display_contract_does_not_treat_an_arbitrary_word_as_enumeration():
    assert backfill.validate_display_contract(
        "question", "Получили x)", "Получили x)",
    ) == (False, "unbalanced_parentheses")


def test_semantic_gate_accepts_indexed_root_as_unicode_root_projection():
    source = "Решите $: ∛(2-x)=1-√(x-1)$"
    display = r"Решите: $\sqrt[3]{2-x}=1-\sqrt{x-1}$"

    assert backfill.semantic_preservation_check(
        source, display, allow_legacy_markup_repair=True,
    ) == (True, "")


def test_semantic_gate_rejects_a_changed_indexed_root_degree():
    source = "Решите ∛(2-x)=0"
    display = r"Решите $\sqrt[4]{2-x}=0$"

    assert backfill.semantic_preservation_check(
        source, display, allow_legacy_markup_repair=True,
    ) == (False, "semantic_number_sequence_changed")


def test_semantic_gate_keeps_russian_source_spelling_immutable():
    assert backfill.semantic_preservation_check(
        "Выберите трех учеников.", "Выберите трёх учеников.",
        allow_legacy_markup_repair=True,
    ) == (False, "semantic_text_sequence_changed")


def test_semantic_gate_accepts_slanted_inequality_command_normalization():
    assert backfill.semantic_preservation_check(
        r"$x\geqslant0$", r"$x \geq 0$", allow_legacy_markup_repair=True,
    ) == (True, "")


def test_semantic_gate_accepts_approximation_command_normalization():
    assert backfill.semantic_preservation_check(
        r"$70/1.5≈45$",
        r"$\dfrac{70}{1.5} \approx 45$",
        allow_legacy_markup_repair=True,
    ) == (True, "")


def test_semantic_gate_accepts_legacy_implication_command_normalization():
    assert backfill.semantic_preservation_check(
        r"$6-a=11-9=>6-a=2=>a=4$",
        r"$6-a=11-9 \Rightarrow 6-a=2 \Rightarrow a=4$",
        allow_legacy_markup_repair=True,
    ) == (True, "")


def test_semantic_gate_rejects_slash_changed_to_colon():
    assert backfill.semantic_preservation_check(
        r"$(16/2=8)$",
        r"$(16:2=8)$",
        allow_legacy_markup_repair=True,
    ) == (False, "semantic_operator_sequence_changed")


@pytest.mark.parametrize(
    ("source", "display"),
    [
        (
            r"Решите систему неравенств: $|x|\le4$, $x^{2}-9>0$.",
            r"Решите систему неравенств: $|x| \leq 4$, $x^{2} - 9 > 0$.",
        ),
        (
            r"Решите систему уравнений: $\sqrt{x^{2}-y^{2}}=x-1$, $y^{2}=2x-1$.",
            r"Решите систему уравнений: $$\begin{cases} "
            r"\sqrt{x^{2} - y^{2}} = x - 1, \\ "
            r"y^{2} = 2x - 1. \end{cases}$$",
        ),
        (
            "Вероятность равна 0,72.",
            r"Вероятность равна $0{,}72$.",
        ),
        (
            r"$x\in(-\infty;5]$",
            r"$x \in (-\infty; 5]$",
        ),
        (
            r"$0$.$12 + 0$.$18 + p = 1$",
            r"$0.12 + 0.18 + p = 1$",
        ),
        (
            r"$x\ge0\Rightarrowx\lev$",
            r"$x \geq 0 \Rightarrow x \leq v$",
        ),
        (
            r"Таблица: $|x|1|2||---|---||P(X=x)|0$.$12|0$.$18|$",
            r"Таблица: $$\begin{array}{c|cc} x & 1 & 2 \\ "
            r"P(X=x) & 0.12 & 0.18 \end{array}$$",
        ),
        (
            r"$\begin{cases}x+y=7\xy=12\end{cases}$",
            r"$$\begin{cases}x+y=7 \\ x\cdot y=12\end{cases}$$",
        ),
        (
            r"$m^{2}\cdotn^{-1}$",
            r"$m^{2} \cdot n^{-1}$",
        ),
        (
            r"1 + \frac{1}{2} \sin^2 2\alpha",
            r"$1 + \dfrac{1}{2} \sin^{2} 2\alpha$",
        ),
        (
            r"$(12+10)/4=5.5$",
            r"$\dfrac{(12+10)}{4}=5.5$",
        ),
        (
            r"Дана функция =f(x)=\cos(2x)$ на $\left[0; " + "\f" + r"rac{\pi}{2}" + "\r" + r"ight]$. Найдите =f^{-1}(x)$.",
            r"Дана функция $f(x)=\cos(2x)$ на $\left[0; \dfrac{\pi}{2}\right]$. Найдите $f^{-1}(x)$.",
        ),
    ],
)
def test_semantic_gate_accepts_equivalent_professional_layout(source, display):
    assert backfill.semantic_preservation_check(
        source, display, allow_legacy_markup_repair=True,
    ) == (True, "")


@pytest.mark.parametrize(
    ("source", "display", "reason"),
    [
        (r"$x\le4$", r"$x \geq 4$", "semantic_operator_sequence_changed"),
        (r"$\sin x=0$", r"$\cos x=0$", "semantic_text_sequence_changed"),
        ("Вероятность равна 0,72.", r"Вероятность равна $0{,}73$.", "semantic_number_sequence_changed"),
        (r"$x+y=4$", r"$x\cdot y=4$", "semantic_operator_sequence_changed"),
        (r"$x\cdot y=4$", r"$x/y=4$", "semantic_operator_sequence_changed"),
    ],
)
def test_semantic_gate_still_rejects_factual_changes_after_layout_normalization(source, display, reason):
    assert backfill.semantic_preservation_check(
        source, display, allow_legacy_markup_repair=True,
    ) == (False, reason)


def test_deepseek_transport_timeout_gets_exactly_one_retry(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    class Session:
        def __init__(self):
            self.calls = 0

        def post(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise requests.Timeout("temporary timeout")
            return Response()

    session = Session()
    monkeypatch.setattr(deepseek_client, "_get_session", lambda: session)
    monkeypatch.setattr(deepseek_client.time, "sleep", lambda _seconds: None)

    result = deepseek_client._post_with_retry(
        "https://example.invalid", {}, {}, timeout=90, max_retries=2,
    )

    assert result == {"ok": True}
    assert session.calls == 2


def test_field_formatter_requires_second_llm_review_before_acceptance(monkeypatch):
    calls = []

    def fake_call(_prompt):
        calls.append(_prompt)
        return "@@FIELD: answer\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\n$2$\n@@END_FIELD"

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", fake_call)

    async def run_bundle():
        return await backfill.format_task_bundle(
            {"answer": "2"}, {"answer": ""}, {"answer": {"raw": "2", "current": ""}},
            asyncio.Semaphore(1),
        )

    result, _seconds = asyncio.run(run_bundle())

    assert len(calls) == 2
    assert "@@SECOND_PASS_INDEPENDENT_REVIEW:" in calls[1]
    assert result["answer"]["llm_self_check_used"] is True
    assert result["answer"]["llm_self_review_ok"] is True


def test_exact_duplicate_value_cannot_bypass_a_final_model_review(monkeypatch):
    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", lambda _prompt: "incomplete")

    async def process() -> dict:
        return await backfill.process_task(
            "task-duplicate",
            "Выберите ответ", "Выберите ответ",
            "1/2", r"$\dfrac{1}{2}$",
            [{"text": "1/3"}],
            [{"text": "1/2"}, {"text": "1/3"}],
            [r"$\dfrac{1}{2}$", r"$\dfrac{1}{3}$"],
            asyncio.Semaphore(1),
            repair_invalid=True,
        )

    result = asyncio.run(process())

    copied = result["field_results"]["dmeta[0].value"]
    assert backfill.field_is_acceptable(copied) is False
    assert copied["decision"] == "REVIEW"


def test_bare_repair_draft_requires_a_separate_explicit_final_review(monkeypatch):
    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return (
                "@@FIELD: answer\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
                "@@REASON: NONE\n@@TEXT:\n$3/4$\n@@END_FIELD"
            )
        if len(calls) == 2:
            # The compact repair prompt may return a plain display draft.
            return r"$\dfrac{3}{4}$"
        return (
            "@@FIELD: answer\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
            "@@REASON: NONE\n@@TEXT:\n$\\dfrac{3}{4}$\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)

    async def run_bundle():
        return await backfill.format_task_bundle(
            {"question": "Вычислите", "answer": "3/4"},
            {"question": "Вычислите", "answer": ""},
            {"answer": {"raw": "3/4", "current": ""}},
            asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    result = results["answer"]
    assert len(calls) == 3
    assert "Верни только готовый русский display-текст" in calls[1]
    assert "@@ОБЯЗАТЕЛЬНЫЙ_АЛГОРИТМ_ИСПРАВЛЕНИЯ:" in calls[1]
    assert "professional_style_requires_dfrac" in calls[1]
    assert "@@SECOND_PASS_INDEPENDENT_REVIEW:" in calls[2]
    assert result["canonical"] == r"$\dfrac{3}{4}$"
    assert result["llm_repair_attempts"] == 1
    assert result["llm_self_review_attempts"] == 1
    assert result["llm_self_review_ok"] is True
    assert result["final_review"]["accepted"] is True
    assert [event["stage"] for event in result["llm_trace"]] == [
        "initial", "repair_1", "final_review_1",
    ]
    assert backfill.field_is_acceptable(result) is True


def test_placeholder_asterisk_repair_is_explicit_and_requires_final_model_review(monkeypatch):
    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return (
                "@@FIELD: question\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
                "@@REASON: NONE\n@@TEXT:\n"
                "Дано трёхзначное число $24*$.\n@@END_FIELD"
            )
        if len(calls) == 2:
            return r"Дано трёхзначное число $24\ast$."
        return (
            "@@FIELD: question\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
            "@@REASON: NONE\n@@TEXT:\n"
            "Дано трёхзначное число $24\\ast$.\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)

    async def run_bundle():
        return await backfill.format_task_bundle(
            {"question": "Дано трёхзначное число 24*."},
            {"question": ""},
            {"question": {"raw": "Дано трёхзначное число 24*.", "current": ""}},
            asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert len(calls) == 3
    assert "professional_style_requires_placeholder_asterisk" in calls[1]
    assert "`24*` -> `$24\\ast$`" in calls[1]
    assert "@@SECOND_PASS_INDEPENDENT_REVIEW:" in calls[2]
    assert results["question"]["canonical"] == r"Дано трёхзначное число $24\ast$."
    assert results["question"]["final_review"]["accepted"] is True


def test_single_missing_parenthesis_is_only_a_model_repair_authorization(monkeypatch):
    raw = "Пояснение (проверка $1$."
    hint = backfill._single_missing_closing_parenthesis_hint(raw)
    assert "ровно одну незакрытую `(`" in hint
    assert "перед финальной пунктуацией" in hint

    calls = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return (
                "@@FIELD: question\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
                "@@REASON: NONE\n@@TEXT:\n"
                "Пояснение ($1$.\n@@END_FIELD"
            )
        if len(calls) == 2:
            return r"Пояснение ($1$)."
        return (
            "@@FIELD: question\n@@DECISION: REPLACE\n@@CONFIDENCE: high\n"
            "@@REASON: NONE\n@@TEXT:\n"
            "Пояснение ($1$).\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)

    async def run_bundle():
        return await backfill.format_task_bundle(
            {"question": raw}, {"question": ""},
            {"question": {"raw": raw, "current": ""}}, asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert len(calls) == 3
    assert "@@ДОПУСК_НА_ВОССТАНОВЛЕНИЕ_СКОБКИ:" in calls[1]
    assert "ровно одну незакрытую `(`" in calls[1]
    assert results["question"]["canonical"] == r"Пояснение ($1$)."
    assert results["question"]["final_review"]["accepted"] is True


def test_focused_dmeta_repair_keeps_task_and_variant_context(monkeypatch):
    calls = []
    raw = r"Ученик получил $(6+10$ или $6+11-1)$."

    def llm(prompt: str) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return (
                "@@FIELD: dmeta[0].description\n@@DECISION: REPLACE\n"
                "@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\n"
                + raw + "\n@@END_FIELD"
            )
        if len(calls) == 2:
            return r"Ученик получил ($6+10$ или $6+11-1$)."
        return (
            "@@FIELD: dmeta[0].description\n@@DECISION: REPLACE\n"
            "@@CONFIDENCE: high\n@@REASON: NONE\n@@TEXT:\n"
            r"Ученик получил ($6+10$ или $6+11-1$)." + "\n@@END_FIELD"
        )

    monkeypatch.setattr(backfill, "call_deepseek_task_bundle", llm)

    async def run_bundle():
        return await backfill.format_task_bundle(
            {
                "question": "Вычислите сумму.",
                "answer": "16",
                "dmeta[0].value": "17",
                "dmeta[0].description": raw,
            },
            {"question": "", "answer": "", "dmeta[0].value": "", "dmeta[0].description": raw},
            {"dmeta[0].description": {"raw": raw, "current": raw}},
            asyncio.Semaphore(1),
        )

    results, _seconds = asyncio.run(run_bundle())

    assert "@@IMMUTABLE_REFERENCE_CONTEXT:" in calls[1]
    assert "@@CONTEXT_FIELD: question\nВычислите сумму." in calls[1]
    assert "@@CONTEXT_FIELD: answer\n16" in calls[1]
    assert "@@CONTEXT_FIELD: dmeta[0].value\n17" in calls[1]
    assert results["dmeta[0].description"]["final_review"]["accepted"] is True


@pytest.mark.parametrize(
    "display",
    [
        r"$x^{2} + y_{1} = \dfrac{3}{4}$",
        r"$x^{\frac{1}{2}} + y_{\frac{2}{3}}$",
        r"Тогда $a \cdot b \leq 5$.",
        r"Дано число $24\ast$.",
        r"$\sqrt{x} \neq \alpha$",
    ],
)
def test_professional_latex_gate_accepts_house_style(display):
    assert backfill.validate_professional_latex(display) == (True, "")


@pytest.mark.parametrize(
    ("display", "reason"),
    [
        (r"$\frac{1}{2}$", "professional_style_requires_dfrac"),
        (r"$x^2 + y_1$", "professional_style_requires_braced_script"),
        (r"$a * b$", "professional_style_requires_cdot"),
        (r"$24*$", "professional_style_requires_placeholder_asterisk"),
        (r"$a \times b$", "professional_style_requires_cdot"),
        (r"$x ≥ 2$", "professional_style_requires_latex_commands"),
        (r"$x \geqslant 2$", "professional_style_requires_standard_inequality_commands"),
        (r"$3/4$", "professional_style_requires_dfrac"),
        (r"$10л$", "professional_style_requires_text_outside_math"),
    ],
)
def test_professional_latex_gate_rejects_non_house_style(display, reason):
    assert backfill.validate_professional_latex(display) == (False, reason)


def test_masked_digit_asterisk_preserves_source_facts_without_becoming_multiplication():
    source = "Дано трёхзначное число 24*."
    rendered = r"Дано трёхзначное число $24\ast$."

    assert backfill.validate_professional_latex(rendered) == (True, "")
    assert backfill.semantic_preservation_check(
        source, rendered, allow_legacy_markup_repair=True,
    ) == (True, "")


def test_bundle_prompt_reports_every_current_style_violation_to_llm():
    current = r"$I_0 + L_1 + 3/4 + 2*5$"
    prompt = backfill._bundle_prompt(
        {"question": "raw"},
        {"question": current},
        {"question": {"raw": "raw", "current": current}},
    )

    assert "@@CURRENT_VALIDATION:" in prompt
    assert "unbraced_script:_0" in prompt
    assert "unbraced_script:_1" in prompt
    assert "bare_fraction:3/4" in prompt
    assert "operator:*" in prompt
    assert "@@RAW_STYLE_LOCATIONS:" not in prompt


def test_bundle_prompt_reports_each_raw_style_location_to_llm():
    raw = r"Получено $I_0 + 3/4 + 2*5 + \frac{1}{2}$."
    prompt = backfill._bundle_prompt(
        {"question": raw},
        {"question": ""},
        {"question": {"raw": raw, "current": ""}},
    )

    assert "@@RAW_STYLE_LOCATIONS:" in prompt
    assert "unbraced_script:_0" in prompt
    assert "bare_fraction:3/4" in prompt
    assert "operator:*" in prompt
    assert r"command:\frac_outside_script" in prompt


def test_bundle_prompt_reports_broken_raw_display_boundaries_to_llm():
    raw = "Получено $(0x=18$; затем $4a+6)$."
    prompt = backfill._bundle_prompt(
        {"question": raw},
        {"question": ""},
        {"question": {"raw": raw, "current": ""}},
    )

    assert "@@RAW_DISPLAY_DIAGNOSTICS:" in prompt
    assert "parenthesis_crosses_math_boundary" in prompt
    assert "@@RAW_BOUNDARY_LOCATIONS:" in prompt
    assert "math_fragment[0] unmatched_opening_(" in prompt
    assert "math_fragment[1] unmatched_closing_)" in prompt
    assert "@@RAW_WITHOUT_LEGACY_DELIMITERS:" in prompt
    assert "Получено (0x=18; затем 4a+6)." in prompt
    assert "Получено $(0x=18$; затем $4a+6)$." not in prompt


def test_bundle_prompt_forbids_review_for_merely_broken_current_display():
    prompt_contract = backfill.SINGLE_FIELD_PROMPT_PREFIX
    assert "Старые `$`, `$$` и их положение НЕ являются фактами" in prompt_contract
    assert "CURRENT_LATEX — только черновик" in prompt_contract
    assert "устранена КАЖДАЯ причина" in prompt_contract
    assert "арифметические `/`, `*`, `\\times` запрещены" in prompt_contract
    assert "не заменяй исходное арифметическое деление `/` двоеточием `:`" in prompt_contract
    assert "`1/(3\\cdot4)` -> `\\dfrac{1}{3\\cdot4}`" in prompt_contract
    assert "`'a'(...)`" in prompt_contract
    assert "`($6+10$ или $6+11-1$)`" in prompt_contract
    assert "`($10$ л)`" in prompt_contract
    assert "Не решай задачу" in prompt_contract
    assert "@@AUDIT_STATUS" not in prompt_contract
    assert "mathematically_invalid" not in prompt_contract
    prompt = backfill._bundle_prompt(
        {"question": r"Вычислите \frac{1}{2}"},
        {"question": r"Вычислите \frac{1}{2}"},
        {"question": {"raw": r"Вычислите \frac{1}{2}", "current": r"Вычислите \frac{1}{2}"}},
    )
    assert "@@REQUIRED_DECISION: REPLACE" in prompt


def test_single_field_prompt_excludes_unrelated_distractor_descriptions():
    prompt = backfill._bundle_prompt(
        {
            "question": "Q", "answer": "A",
            "dmeta[0].value": "D0", "dmeta[0].description": "DESC0",
            "dmeta[1].value": "D1", "dmeta[1].description": "DESC1",
        },
        {},
        {"dmeta[0].description": {"raw": "DESC0", "current": ""}},
    )

    assert "@@TARGET_FIELD: dmeta[0].description" in prompt
    assert "@@FIELD_CONTEXT: question" in prompt
    assert "@@FIELD_CONTEXT: answer" in prompt
    assert "@@FIELD_CONTEXT: dmeta[0].value" in prompt
    assert "@@FIELD_CONTEXT: dmeta[0].description" in prompt
    assert "@@FIELD_CONTEXT: dmeta[1].value" not in prompt
    assert "@@FIELD_CONTEXT: dmeta[1].description" not in prompt


def test_split_decimal_boundary_is_explicitly_sent_to_llm_for_repair():
    raw = r"Вычислите $5$, $2 \cdot 0$, $4$"
    prompt = backfill._bundle_prompt(
        {"question": raw, "answer": "$2,08$"},
        {"question": raw, "answer": "$2,08$"},
        {"question": {"raw": raw, "current": raw}},
    )

    assert "@@RAW_WITHOUT_LEGACY_DELIMITERS:" in prompt
    assert "@@LEGACY_DECIMAL_BOUNDARY_CANDIDATES:" in prompt
    assert "legacy_split_decimal_math_boundary" in prompt
    assert "@@REQUIRED_DECISION: REPLACE" in prompt


def test_punctuation_only_math_fragment_is_explicitly_sent_to_llm_for_repair():
    raw = "Запишите ответ $.$"
    prompt = backfill._bundle_prompt(
        {"question": raw}, {"question": raw},
        {"question": {"raw": raw, "current": raw}},
    )

    assert "@@LEGACY_PUNCTUATION_ONLY_MATH:" in prompt
    assert "legacy_punctuation_only_math_fragment" in prompt


@pytest.mark.parametrize(
    ("source", "display", "reason"),
    [
        ("x = 15/8", r"$x = \dfrac{15}{9}$", "semantic_number_sequence_changed"),
        ("x + y", "$x - y$", "semantic_operator_sequence_changed"),
        ("Найдите x", "$x$", "semantic_text_sequence_changed"),
    ],
)
def test_semantic_gate_rejects_source_edits(source, display, reason):
    ok, actual_reason = backfill.semantic_preservation_check(source, display)

    assert ok is False
    assert actual_reason == reason


def _result(dmeta):
    return {
        "task_id": "task-1",
        "original": {
            "question": "Найдите x",
            "question_latex": "",
            "answer": "2",
            "correct_answer_latex": "",
        },
        "dmeta_original": dmeta,
        "canonical_fingerprint": backfill.canonical_fingerprint("Найдите x", "2", dmeta),
        "field_results": {
            "question": _accepted("Найдите $x$"),
            "answer": _accepted("$2$"),
            "dmeta[0].value": _accepted("$1$"),
            "dmeta[0].description": _accepted(r"Исходная логика с $2$"),
        },
    }


def test_canonical_fingerprint_ignores_only_display_fields():
    source = [{"value": "1", "explanation": "Исходное объяснение", "error_logic": "Исходная логика"}]
    with_display = [{**source[0], "value_latex": "$1$", "explanation_latex": "LaTeX"}]

    assert backfill.canonical_fingerprint("Q", "A", source) == backfill.canonical_fingerprint("Q", "A", with_display)

    changed_raw = [{**with_display[0], "explanation": "Подменённое объяснение"}]
    assert backfill.canonical_fingerprint("Q", "A", source) != backfill.canonical_fingerprint("Q", "A", changed_raw)


def test_canonical_fingerprint_treats_null_and_empty_collections_as_same():
    assert backfill.canonical_fingerprint("Q", "A", None, None) == backfill.canonical_fingerprint(
        "Q", "A", [], [],
    )


def test_save_result_adds_display_fields_without_changing_raw_distractor_data():
    source = [{"value": "1", "explanation": "Исходное объяснение", "error_logic": "Исходная логика"}]
    conn = _Connection(("Найдите x", "2", source))

    backfill.save_result(conn, _result(source))

    update_sql, params = conn.writes[0]
    assert "UPDATE tasks_master" in update_sql
    saved = json.loads(params["dmeta"])
    assert saved[0]["value"] == "1"
    assert saved[0]["explanation"] == "Исходное объяснение"
    assert saved[0]["error_logic"] == "Исходная логика"
    assert saved[0]["value_latex"] == "$1$"
    assert saved[0]["error_logic_latex"] == "Исходная логика с $2$"
    assert "explanation_latex" not in saved[0]


def test_save_result_appends_a_durable_audit_revision_for_an_executed_run():
    source = [{"value": "1", "explanation": "Исходное объяснение", "error_logic": "Исходная логика"}]
    result = _result(source)
    result["original"].update({"answer_options": [], "answer_options_latex": []})
    result["run_context"] = {
        "run_id": "d7d96a31-d0b0-4c5a-9e42-7c8f29911a08",
        "model": backfill.LATEX_BACKFILL_MODEL,
        "prompt_version": backfill.LATEX_BACKFILL_PROMPT_VERSION,
        "policy_version": backfill.LATEX_BACKFILL_POLICY_VERSION,
    }
    result["field_results"]["question"]["final_review"] = {
        "accepted": True,
        "verdict": "accepted_after_independent_final_review",
    }
    result["field_results"]["question"]["llm_trace"] = [{
        "stage": "final_review_1", "prompt_sha256": "a" * 64,
        "response_sha256": "b" * 64, "error": None,
    }]
    conn = _Connection(("Найдите x", "2", source, [], "", "", [], None))

    backfill.save_result(conn, result)

    audit_writes = [
        (sql, params) for sql, params in conn.writes
        if "INSERT INTO task_latex_change_audit" in sql
    ]
    assert len(audit_writes) == 1
    _sql, params = audit_writes[0]
    assert params["run_id"] == result["run_context"]["run_id"]
    assert params["task_id"] == "task-1"
    assert params["event_type"] == "write"
    assert params["source_fingerprint"] == result["canonical_fingerprint"]
    before = json.loads(params["before_snapshot"])
    after = json.loads(params["after_snapshot"])
    assert before["question_latex"] == ""
    assert after["question_latex"] == "Найдите $x$"
    evidence = json.loads(params["validation"])
    assert evidence["field_results"]["question"]["final_review"]["accepted"] is True
    assert evidence["field_results"]["question"]["llm_trace"][0]["stage"] == "final_review_1"
    assert result["audit_id"]


def test_save_result_preserves_null_distractor_meta_exactly():
    result = _result(None)
    result["field_results"].pop("dmeta[0].value")
    result["field_results"].pop("dmeta[0].description")
    result["canonical_fingerprint"] = backfill.canonical_fingerprint(
        "Найдите x", "2", None, [],
    )
    conn = _Connection(("Найдите x", "2", None, [], "", "", None, None))

    backfill.save_result(conn, result)

    update_sql, params = conn.writes[0]
    assert "UPDATE tasks_master" in update_sql
    assert params["dmeta"] is None


def test_save_result_refuses_a_concurrent_canonical_change():
    source = [{"value": "1", "explanation": "Исходное объяснение"}]
    conn = _Connection(("Найдите x", "2", [{"value": "1", "explanation": "Изменено редактором"}]))

    with pytest.raises(RuntimeError, match="changed concurrently"):
        backfill.save_result(conn, _result(source))

    assert conn.writes == []


def test_save_result_keeps_verified_when_rejected_suggestion_leaves_valid_display_intact():
    source = [{
        "value": "1", "value_latex": "$1$",
        "error_logic": "Исходная логика с 2", "error_logic_latex": "Исходная логика с $2$",
    }]
    result = _result(source)
    result["original"].update({
        "question_latex": "Найдите $x$",
        "correct_answer_latex": "$2$",
        "answer_options": [],
        "answer_options_latex": [],
    })
    rejected = {**_accepted("Найдите $x$"), "confidence": "low", "ambiguity_reason": "llm_timeout"}
    result["field_results"]["question"] = rejected
    conn = _Connection((
        "Найдите x", "2", source, [], "Найдите $x$", "$2$", [], None,
    ))

    backfill.save_result(conn, result)

    update_sql, params = conn.writes[0]
    assert "UPDATE tasks_master" in update_sql
    assert params["status"] == "verified"


def test_save_result_skips_physical_update_when_keep_audit_changes_nothing():
    source = [{
        "value": "1", "value_latex": "$1$",
        "error_logic": "Ошибка", "error_logic_latex": "Ошибка",
    }]
    result = _result(source)
    result["original"].update({
        "question_latex": "Найдите $x$",
        "correct_answer_latex": "$2$",
        "answer_options": [],
        "answer_options_latex": [],
    })
    result["field_results"] = {}
    result["canonical_fingerprint"] = backfill.canonical_fingerprint(
        "Найдите x", "2", source, [],
    )
    conn = _Connection((
        "Найдите x", "2", source, [], "Найдите $x$", "$2$", [], "verified",
    ))

    backfill.save_result(conn, result)

    assert not any("UPDATE tasks_master" in sql for sql, _params in conn.writes)
    assert any("UPDATE review_queue" in sql for sql, _params in conn.writes)
    assert result["stored_status"] == "verified"
    assert result["database_write"] == "skipped_unchanged"


def test_save_result_cannot_verify_an_unprocessed_but_invalid_existing_field():
    source = [{
        "value": "1", "value_latex": "1",
        "error_logic": "Ошибка", "error_logic_latex": "Ошибка",
    }]
    result = _result(source)
    result["original"].update({
        "question_latex": "Найдите $x$",
        "correct_answer_latex": "$2$",
        "answer_options": [],
        "answer_options_latex": [],
    })
    result["field_results"] = {}
    result["canonical_fingerprint"] = backfill.canonical_fingerprint(
        "Найдите x", "2", source, [],
    )
    conn = _Connection((
        "Найдите x", "2", source, [], "Найдите $x$", "$2$", [], None,
    ))

    backfill.save_result(conn, result)

    update_sql, params = conn.writes[0]
    assert "UPDATE tasks_master" in update_sql
    assert params["status"] == "partial"


def test_timeout_result_cannot_mark_task_verified_when_required_display_is_missing():
    """A transport timeout must never be mistaken for a successful LLM audit."""
    source = [{
        "value": "1",
        "error_logic": "Исходная логика с 2",
    }]
    result = _result(source)
    result["original"].update({
        "answer_options": [],
        "answer_options_latex": [],
    })
    result["field_results"]["question"] = {
        "canonical": "",
        "decision": "REVIEW",
        "confidence": "low",
        "ambiguity_reason": "llm_error: Request timeout",
        "katex_ok": True,
        "katex_error": "",
        "contract_ok": False,
        "contract_error": "required_display_missing",
        "professional_ok": True,
        "professional_error": "",
        "semantic_ok": False,
        "semantic_error": "not_checked_due_to_llm_error",
    }
    result["canonical_fingerprint"] = backfill.canonical_fingerprint(
        "Найдите x", "2", source, [],
    )
    conn = _Connection((
        "Найдите x", "2", source, [], "", "", [], None,
    ))

    backfill.save_result(conn, result)

    update_sql, params = conn.writes[0]
    assert "UPDATE tasks_master" in update_sql
    assert params["status"] == "partial"
    assert params["ql"] == ""
    review_updates = [
        params for sql, params in conn.writes
        if "UPDATE review_queue" in sql and "ai_suggestion" in sql
    ]
    assert len(review_updates) == 1
    suggestion = json.loads(review_updates[0]["suggestion"])
    assert suggestion["question"]["reason"] == "missing_display_value"
    assert suggestion["question"]["attempt_reason"] == "llm_error: Request timeout"


def test_fill_only_mode_does_not_resubmit_complete_display_fields_to_llm():
    complete_dmeta = [{
        "value": "1", "value_latex": "$1$",
        "explanation": "Исходное объяснение", "explanation_latex": "Исходное объяснение",
    }]

    async def process() -> dict:
        return await backfill.process_task(
            "task-1", "Найдите x", "Найдите $x$", "2", "$2$", complete_dmeta,
            [], [], asyncio.Semaphore(1),
        )

    result = asyncio.run(process())

    assert result["field_results"] == {}
    assert result["original"]["question_latex"] == "Найдите $x$"
    assert result["original"]["correct_answer_latex"] == "$2$"


def test_audit_queue_selection_includes_only_display_repairs(tmp_path):
    queue = tmp_path / "display-audit.json"
    queue.write_text(json.dumps({
        "mode": "read_only",
        "records": [
            {"task_id": "task-display-1", "kind": "display_repair"},
            {"task_id": "task-status-only", "kind": "status_only"},
            {"task_id": "task-display-2", "kind": "display_repair"},
            {"task_id": "task-display-1", "kind": "display_repair"},
        ],
    }), encoding="utf-8")

    assert backfill.load_audit_display_ids(str(queue)) == [
        "task-display-1", "task-display-2",
    ]


def test_audit_queue_selection_retains_source_fingerprints_and_file_hash(tmp_path):
    queue = tmp_path / "display-audit.json"
    first = "a" * 64
    queue.write_text(json.dumps({
        "mode": "read_only",
        "records": [
            {
                "task_id": "task-display-1", "kind": "display_repair",
                "canonical_fingerprint_sha256": first,
            },
            {"task_id": "task-status-only", "kind": "status_only"},
        ],
    }), encoding="utf-8")

    ids, fingerprints, file_hash = backfill.load_audit_display_selection(str(queue))

    assert ids == ["task-display-1"]
    assert fingerprints == {"task-display-1": first}
    assert len(file_hash) == 64


def test_audit_queue_selection_rejects_non_audit_document(tmp_path):
    queue = tmp_path / "not-an-audit.json"
    queue.write_text(json.dumps({"mode": "write", "records": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="read-only audit"):
        backfill.load_audit_display_ids(str(queue))


def test_save_result_records_attestation_and_updates_tags_for_independently_reviewed_fields():
    source = [{"value": "1", "explanation": "Исходное объяснение", "error_logic": "Исходная логика"}]
    result = _result(source)
    result["original"].update({"answer_options": [], "answer_options_latex": []})
    result["run_context"] = {
        "run_id": "d7d96a31-d0b0-4c5a-9e42-7c8f29911a08",
        "model": backfill.LATEX_BACKFILL_MODEL,
        "prompt_version": backfill.LATEX_BACKFILL_PROMPT_VERSION,
        "policy_version": backfill.LATEX_BACKFILL_POLICY_VERSION,
    }
    result["field_results"]["question"]["final_review"] = {
        "required": True,
        "completed": True,
        "accepted": True,
        "verdict": "accepted_after_independent_final_review",
    }
    result["field_results"]["answer"]["final_review"] = {
        "required": True,
        "completed": True,
        "accepted": True,
        "verdict": "accepted_after_independent_final_review",
    }
    conn = _Connection(("Найдите x", "2", source, [], "", "", [], None))

    backfill.save_result(conn, result)

    attestation_writes = [
        (sql, params) for sql, params in conn.writes
        if "INSERT INTO task_latex_display_attestations" in sql
    ]
    assert len(attestation_writes) == 2
    q_att = next(p for s, p in attestation_writes if p["field_key"] == "question")
    assert q_att["task_id"] == "task-1"
    assert q_att["source_value"] == "Найдите x"
    assert q_att["display_value"] == "Найдите $x$"
    assert len(q_att["source_sha256"]) == 64
    assert len(q_att["display_sha256"]) == 64

    tags_updates = [
        (sql, params) for sql, params in conn.writes
        if "UPDATE tasks_master" in sql and "latex_attested_fields" in sql
    ]
    assert len(tags_updates) == 1
    attested_labels = json.loads(tags_updates[0][1]["attested_json"])
    assert "question" in attested_labels
    assert "answer" in attested_labels


def test_task_row_full_exposes_attested_fields():
    from src.api.content_router import _task_row_full
    row = (
        "task-1", "skill-1", "Навык", "B", "Условие", "Условие $x$",
        "mcq", "2", "$2$", ["2", "1"], ["$2$", "$1$"], [{"value": "1"}],
        1.2, -0.3, 0.25, "verified", "verified", True,
        {"latex_attested_fields": ["question", "answer"]}, None,
    )
    task = _task_row_full(row)
    assert task["attested_fields"] == ["question", "answer"]

