from src.pipeline.distractors import _apply_pedagogy_inline, _build_distractor_prompt
from src.pipeline.distractor_pedagogy import _build_prompt as _build_pedagogy_prompt
from src.pipeline.models import ExtractedTask
from types import SimpleNamespace

from src.pipeline.smart_verify import (
    _build_compute_prompt,
    _question_has_missing_choice_content,
    _requires_response_route,
    run_smart_verify_pipeline,
)
from src.pipeline.smart_verify_mcq import _build_mcq_prompt
from src.pipeline.smart_verify_text import _build_text_prompt, run_text_verify_pipeline
from src.pipeline.smart_verify_common import clear_stale_verify_flags, verification_status
from src.schemas.smart_verify import (
    PedagogyItemReview,
    PedagogyReviewResponse,
    SmartVerifyResponse,
    TextVerifyResponse,
)


def test_verify_prompts_request_only_verification_outputs():
    compute = _build_compute_prompt("T1", "Сколько будет 2 + 2?", "exact_number", "4")
    text = _build_text_prompt("T2", "Ответьте на вопрос", "ответ")
    mcq = _build_mcq_prompt("T3", "Выберите верный ответ", "A")

    assert "step_by_step_solution" not in compute
    assert "step_by_step_solution" not in text
    assert "step_by_step_solution" not in mcq


def test_verify_schemas_do_not_require_or_store_steps():
    compute = SmartVerifyResponse(
        sympy_compatible_string="Integer(4)",
        absolute_correct_answer="4",
    )
    text = TextVerifyResponse(absolute_correct_answer="4", confidence="high")

    assert not hasattr(compute, "step_by_step_solution")
    assert not hasattr(text, "step_by_step_solution")


def test_distractor_prompt_uses_task_and_verified_answer_not_old_steps():
    task = ExtractedTask(
        temp_id="T4",
        question_text="Сколько будет 2 + 2?",
        answer_raw="4",
        answer_type="exact_number",
        tags={"step_by_step_solution": "устаревшее и неверное решение"},
    )

    prompt = _build_distractor_prompt(task, "4")

    assert "Сколько будет 2 + 2?" in prompt
    assert "Правильный ответ: 4" in prompt
    assert "устаревшее и неверное решение" not in prompt
    assert "error_logic" in prompt


def test_long_non_generic_distractor_logic_is_still_pedagogy_reviewed(monkeypatch):
    task = ExtractedTask(
        temp_id="T5",
        question_text="Сколько будет 2 + 2?",
        answer_raw="4",
        answer_type="exact_number",
    )
    candidates = [
        {
            "value": "5",
            "error_logic": "Ученик прибавил к первому слагаемому лишнюю единицу и получил пять.",
        },
        {
            "value": "3",
            "error_logic": "Ученик вычел единицу из промежуточного результата и получил три.",
        },
    ]
    calls = []

    def fake_audit(**kwargs):
        calls.append(kwargs)
        return PedagogyReviewResponse(
            overall="pass",
            items=[
                PedagogyItemReview(index=0, status="ok"),
                PedagogyItemReview(index=1, status="ok"),
            ],
        )

    monkeypatch.setattr(
        "src.pipeline.distractor_pedagogy.audit_distractor_pedagogy",
        fake_audit,
    )

    reviewed, passed = _apply_pedagogy_inline(candidates, task, "4", [])

    assert passed is True
    assert reviewed == candidates
    assert len(calls) == 1


def test_answer_success_is_not_verified_until_distractors_are_complete():
    assert verification_status({"smart_verify_status": "verified_match"}) == "pending"
    assert verification_status(
        {
            "smart_verify_status": "verified_match",
            "choices_complete": True,
            "distractor_regen_pending": True,
        }
    ) == "pending"
    assert verification_status(
        {"smart_verify_status": "verified_match", "choices_complete": True}
    ) == "verified"


def test_prose_verdict_is_not_replaced_with_a_bare_numeric_answer(monkeypatch):
    def fake_compute(*_args, **_kwargs):
        return (
            SimpleNamespace(
                absolute_correct_answer="6",
                sympy_compatible_string="6",
            ),
            SimpleNamespace(ok=True, reason="sympy_match", computed_local="6"),
            "6",
        )

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    result = run_smart_verify_pipeline(
        task_id="PROSE1",
        question="Ученик вычислил интеграл и получил 6. Проверьте ответ.",
        correct_answer="Неверно, правильный ответ: $6$",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
    )

    assert result["correct_answer"] == "Неверно, правильный ответ: $6$"
    assert result["verification_status"] == "pending"
    assert result["tags"]["smart_verify_status"] == "needs_human_review"
    assert result["tags"]["answer_format_review_required"] is True


def test_arbitration_corrects_only_after_three_unanimous_gated_solves(monkeypatch):
    """A source answer may change only after complete unanimous evidence."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    calls = []

    def fake_compute(*_args, **_kwargs):
        calls.append(True)
        response = SmartVerifyResponse(
            absolute_correct_answer="9",
            sympy_compatible_string="Integer(9)",
        )
        return response, SympyGateResult(
            ok=True, computed_local="9", reason="sympy_match",
        ), "9"

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    monkeypatch.setattr(
        "src.pipeline.smart_verify.resolve_canonical_answer",
        lambda *_args, **_kwargs: ("9", "test"),
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify.apply_distractors",
        lambda **kwargs: (kwargs["dmeta"], kwargs["tags"], kwargs["action"]),
    )

    result = run_smart_verify_pipeline(
        task_id="ARBITRATION_UNANIMOUS",
        question="Вычислите значение выражения.",
        correct_answer="81",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
        answer_authority="textbook",
        require_unanimous_consensus=True,
        allow_source_correction=True,
    )

    assert len(calls) == 3
    assert result["correct_answer"] == "9"
    assert result["tags"]["smart_verify_status"] == "verified_corrected"
    assert result["tags"]["smart_verify_arbitration_votes"] == ["9", "9", "9"]
    assert result["tags"]["smart_verify_consensus_unanimous"] is True


def test_arbitration_refuses_a_two_to_one_majority(monkeypatch):
    """A 2:1 vote is review evidence, never permission to correct a source."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    candidates = iter(("9", "9", "8"))

    def fake_compute(*_args, **_kwargs):
        candidate = next(candidates)
        response = SmartVerifyResponse(
            absolute_correct_answer=candidate,
            sympy_compatible_string=f"Integer({candidate})",
        )
        return response, SympyGateResult(
            ok=True, computed_local=candidate, reason="sympy_match",
        ), candidate

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    monkeypatch.setattr(
        "src.pipeline.smart_verify.resolve_canonical_answer",
        lambda *_args, **_kwargs: ("9", "test"),
    )

    result = run_smart_verify_pipeline(
        task_id="ARBITRATION_SPLIT",
        question="Вычислите значение выражения.",
        correct_answer="81",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
        answer_authority="textbook",
        require_unanimous_consensus=True,
        allow_source_correction=True,
    )

    assert result["correct_answer"] == "81"
    assert result["tags"]["smart_verify_status"] == "needs_human_review"
    assert result["tags"]["smart_verify_arbitration_reason"] == "non_unanimous_consensus"
    assert result["tags"]["self_consistency_votes"] == ["9", "9", "8"]


def test_arbitration_still_requires_three_solves_when_source_matches(monkeypatch):
    """A matching first answer cannot bypass the three-way arbitration gate."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    calls = []

    def fake_compute(*_args, **_kwargs):
        calls.append(True)
        response = SmartVerifyResponse(
            absolute_correct_answer="9",
            sympy_compatible_string="Integer(9)",
        )
        return response, SympyGateResult(
            ok=True, computed_local="9", reason="sympy_match",
        ), "9"

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    monkeypatch.setattr(
        "src.pipeline.smart_verify.resolve_canonical_answer",
        lambda *_args, **_kwargs: ("9", "test"),
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify.apply_distractors",
        lambda **kwargs: (kwargs["dmeta"], kwargs["tags"], kwargs["action"]),
    )

    result = run_smart_verify_pipeline(
        task_id="ARBITRATION_MATCH",
        question="Вычислите значение выражения.",
        correct_answer="9",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
        answer_authority="textbook",
        require_unanimous_consensus=True,
        allow_source_correction=True,
    )

    assert len(calls) == 3
    assert result["tags"]["smart_verify_status"] == "verified_match"
    assert result["tags"]["smart_verify_arbitration_votes"] == ["9", "9", "9"]


def test_text_arbitration_accepts_three_matching_answers_without_sympy(monkeypatch):
    """A semantic answer is proven by three matching solves, not SymPy."""
    calls = []

    def fake_text_llm(*_args, **_kwargs):
        calls.append(True)
        return TextVerifyResponse(absolute_correct_answer="Да", confidence="high")

    monkeypatch.setattr(
        "src.pipeline.smart_verify_text._run_text_llm", fake_text_llm,
    )
    # The text route must ignore an incidental local arithmetic result once
    # it is running the three-solver arbitration.
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text.compute_answer_from_question",
        lambda _question: "17",
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text.is_high_confidence_arithmetic",
        lambda _question: True,
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text.apply_distractors",
        lambda **kwargs: (kwargs["dmeta"], kwargs["tags"], kwargs["action"]),
    )

    result = run_text_verify_pipeline(
        task_id="TEXT_TRIPLE",
        question="Верно ли утверждение?",
        correct_answer="Да",
        answer_type="text",
        distractor_meta=[],
        tags={},
        require_unanimous_consensus=True,
    )

    assert len(calls) == 3
    assert result["correct_answer"] == "Да"
    assert result["tags"]["smart_verify_status"] == "verified_match"
    assert result["tags"]["smart_verify_consensus_unanimous"] is True
    assert result["tags"]["smart_verify_arbitration_votes"] == ["Да", "Да", "Да"]


def test_text_arbitration_preserves_equivalent_source_wording(monkeypatch):
    """Unanimous prose must not rewrite a source merely for grammar/style."""
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text._run_text_llm",
        lambda *_args, **_kwargs: TextVerifyResponse(
            absolute_correct_answer="квадратный метр", confidence="high",
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text._compare_text_source_relation",
        lambda **_kwargs: "equivalent",
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text.apply_distractors",
        lambda **kwargs: (kwargs["dmeta"], kwargs["tags"], kwargs["action"]),
    )

    result = run_text_verify_pipeline(
        task_id="TEXT_EQUIVALENT",
        question="В каких единицах измеряют площадь?",
        correct_answer="квадратные метры",
        answer_type="text",
        distractor_meta=[],
        tags={},
        require_unanimous_consensus=True,
    )

    assert result["correct_answer"] == "квадратные метры"
    assert result["tags"]["smart_verify_status"] == "verified_match"
    assert result["tags"]["answer_format_preserved"] is True


def test_text_arbitration_never_rewrites_source_on_unanimous_mismatch(monkeypatch):
    """Three matching model answers are evidence, not a source rewrite right."""
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text._run_text_llm",
        lambda *_args, **_kwargs: TextVerifyResponse(
            absolute_correct_answer="да, является тождеством", confidence="high",
        ),
    )
    result = run_text_verify_pipeline(
        task_id="TEXT_SOURCE_MISMATCH",
        question="Является ли равенство тождеством?",
        correct_answer="Нет, не является тождеством при x=2",
        answer_type="text",
        distractor_meta=[],
        tags={},
        require_unanimous_consensus=True,
    )

    assert result["correct_answer"] == "Нет, не является тождеством при x=2"
    assert result["verification_status"] == "pending"
    assert result["tags"]["smart_verify_status"] == "needs_human_review"
    assert result["tags"]["answer_source_review_required"] is True


def test_arbitration_never_drops_integration_constant(monkeypatch):
    """Derivative equivalence is insufficient to remove the required ``+ C``."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    def fake_compute(*_args, **_kwargs):
        response = SmartVerifyResponse(
            absolute_correct_answer="(2*x - 1)*exp(2*x)/4",
            sympy_compatible_string="(2*x - 1)*exp(2*x)/4",
        )
        return response, SympyGateResult(
            ok=True,
            computed_local="(2*x - 1)*exp(2*x)/4",
            reason="sympy_match",
        ), "(2*x - 1)*exp(2*x)/4"

    source = "$\\frac{1}{4}e^{2x}(2x-1)+C$"
    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    monkeypatch.setattr(
        "src.pipeline.smart_verify.apply_distractors",
        lambda **kwargs: (kwargs["dmeta"], kwargs["tags"], kwargs["action"]),
    )

    result = run_smart_verify_pipeline(
        task_id="INTEGRAL_C",
        question="Найдите первообразную функции.",
        correct_answer=source,
        answer_type="expression",
        distractor_meta=[],
        tags={},
        require_unanimous_consensus=True,
        allow_source_correction=True,
    )

    assert result["correct_answer"] == source
    assert result["tags"]["smart_verify_status"] == "verified_match"
    assert (
        result["tags"]["smart_verify_arbitration_format_guard"]
        == "preserved_integration_constant"
    )


def test_arbitration_skips_a_missing_question_before_any_llm(monkeypatch):
    """An orphaned answer/options record is content repair, not arithmetic."""
    calls = []
    monkeypatch.setattr(
        "src.pipeline.smart_verify._run_single_compute",
        lambda *_args, **_kwargs: calls.append(True),
    )

    result = run_smart_verify_pipeline(
        task_id="NO_QUESTION",
        question="",
        correct_answer="3",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
        require_unanimous_consensus=True,
        allow_source_correction=True,
    )

    assert calls == []
    assert result["tags"]["smart_verify_status"] == "needs_content_repair"
    assert result["tags"]["content_repair_reason"] == "missing_question_text"


def test_choice_stem_without_choices_is_content_repair():
    assert _question_has_missing_choice_content(
        "Какое из уравнений не является биквадратным?"
    )
    assert not _question_has_missing_choice_content(
        "Какое из уравнений верно?\nА) $x=1$\nБ) $x=2$"
    )


def test_percent_format_is_not_lost_and_keeps_requested_rounding():
    from src.pipeline.answer_verify import answers_equivalent

    assert answers_equivalent(r"$0.8\%$", r"0.840336\%", "exact_number")
    assert not answers_equivalent(r"$0.8\%$", "0.8", "exact_number")


def test_response_router_keeps_a_semantic_no_parameter_answer_out_of_text_mode():
    assert not _requires_response_route("exact_number", "Ни при каком $a$")


def test_ordinary_semantic_route_requires_three_answers(monkeypatch):
    """Text answers never use the one-pass mathematical verification path."""
    captured = {}

    def fake_text(**kwargs):
        captured.update(kwargs)
        return {
            "status": "success",
            "correct_answer": "Да",
            "distractor_meta": [],
            "tags": {"smart_verify_status": "verified_match"},
            "action": "verified_match",
            "verification_status": "pending",
        }

    monkeypatch.setattr("src.pipeline.smart_verify.run_text_verify_pipeline", fake_text)
    run_smart_verify_pipeline(
        task_id="TEXT_ORDINARY",
        question="Верно ли утверждение?",
        correct_answer="Да",
        answer_type="text",
        distractor_meta=[],
        tags={},
    )

    assert captured["require_unanimous_consensus"] is True


def test_ordinary_math_route_does_not_require_three_answers(monkeypatch):
    """A numerical task remains governed by the local SymPy gate."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    calls = []

    def fake_compute(*_args, **_kwargs):
        calls.append(True)
        return (
            SmartVerifyResponse(
                absolute_correct_answer="4", sympy_compatible_string="Integer(4)",
            ),
            SympyGateResult(ok=True, computed_local="4", reason="sympy_match"),
            "4",
        )

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    monkeypatch.setattr(
        "src.pipeline.smart_verify.apply_distractors",
        lambda **kwargs: (kwargs["dmeta"], kwargs["tags"], kwargs["action"]),
    )
    run_smart_verify_pipeline(
        task_id="MATH_ORDINARY",
        question="Вычислите 2+2.",
        correct_answer="4",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
    )

    assert len(calls) == 1


def test_textbook_authority_preserves_a_text_answer_on_llm_mismatch(monkeypatch):
    """A content-verification pass may never silently rewrite source prose."""
    captured = {}

    def fake_text(**kwargs):
        captured.update(kwargs)
        return {
            "status": "review",
            "correct_answer": kwargs["correct_answer"],
            "distractor_meta": kwargs["distractor_meta"],
            "tags": {"smart_verify_status": "needs_human_review"},
            "action": "needs_human_review_source_preserved",
            "verification_status": "pending",
        }

    monkeypatch.setattr("src.pipeline.smart_verify.run_text_verify_pipeline", fake_text)
    result = run_smart_verify_pipeline(
        task_id="TEXTBOOK_TEXT",
        question="Верно ли утверждение?",
        correct_answer="Нет, утверждение неверно.",
        answer_type="text",
        distractor_meta=[],
        tags={},
        answer_authority="textbook",
    )

    assert captured["preserve_source_on_mismatch"] is True
    assert result["correct_answer"] == "Нет, утверждение неверно."


def test_invalid_code_execution_uses_gated_structured_fallback(monkeypatch):
    """A broken generated program may not turn into an unverified answer."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    def fail_code(*_args, **_kwargs):
        raise RuntimeError("NameError: a_val")

    fallback_calls = []

    def structured(*_args, **_kwargs):
        fallback_calls.append(True)
        return SmartVerifyResponse(
            sympy_compatible_string="Integer(4)",
            absolute_correct_answer="4",
        )

    monkeypatch.setattr("src.pipeline.smart_verify.call_deepseek_code_execution", fail_code)
    monkeypatch.setattr("src.pipeline.smart_verify.call_deepseek_structured", structured)
    monkeypatch.setattr(
        "src.pipeline.smart_verify._gate_compute_response",
        lambda response, *_args, **_kwargs: (
            response,
            SympyGateResult(ok=True, computed_local="4", reason="sympy_match"),
            "4",
        ),
    )

    from src.pipeline.smart_verify import _run_single_compute

    response, gate, canonical = _run_single_compute(
        "FALLBACK1", "Вычислите 2 + 2.", "exact_number", "4"
    )

    assert fallback_calls == [True]
    assert response.absolute_correct_answer == "4"
    assert gate.ok is True
    assert canonical == "4"


def test_known_boolean_failure_goes_directly_to_structured_fallback(monkeypatch):
    """A previously observed True/False proof must not spend another code run."""
    from src.pipeline.answer_sympy_gate import SympyGateResult
    from src.pipeline.smart_verify import _run_single_compute

    monkeypatch.setattr(
        "src.pipeline.smart_verify.call_deepseek_code_execution",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("known boolean failure must skip code route")
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify.call_deepseek_structured",
        lambda *_args, **_kwargs: SmartVerifyResponse(
            sympy_compatible_string="Rational(3, 10)",
            absolute_correct_answer="3/10",
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify._gate_compute_response",
        lambda response, *_args, **_kwargs: (
            response,
            SympyGateResult(ok=True, computed_local="3/10", reason="sympy_match"),
            "3/10",
        ),
    )

    _response, gate, canonical = _run_single_compute(
        "BOOLEAN_DIRECT", "Сравните дроби.", "exact_number", "3/10",
        prior_gate_error="invalid_boolean_result",
    )

    assert gate.ok is True
    assert canonical == "3/10"


def test_local_mismatch_does_not_spend_a_fallback_model_call(monkeypatch):
    """A mathematical conflict must stay reviewable instead of being retried away."""
    from src.pipeline.answer_sympy_gate import SympyGateResult

    code_response = SmartVerifyResponse(
        sympy_compatible_string="Integer(5)", absolute_correct_answer="5"
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify.call_deepseek_code_execution",
        lambda *_args, **_kwargs: code_response,
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify.call_deepseek_structured",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("mismatch must not invoke fallback")
        ),
    )
    mismatch = SympyGateResult(
        ok=False, computed_local="4", reason="local_mismatch: '4' vs '5'"
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify._gate_compute_response",
        lambda response, *_args, **_kwargs: (response, mismatch, None),
    )

    from src.pipeline.smart_verify import _run_single_compute

    response, gate, canonical = _run_single_compute(
        "MISMATCH1", "Вычислите 2 + 2.", "exact_number", "4"
    )

    assert response is code_response
    assert gate.reason.startswith("local_mismatch")
    assert canonical is None


def test_saved_model_evidence_is_regated_without_another_model_call(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("a saved response must not invoke the model again")

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fail_if_called)
    result = run_smart_verify_pipeline(
        task_id="REPLAY1",
        question="Вычислите 1/2 + 1/2.",
        correct_answer="1",
        answer_type="exact_number",
        distractor_meta=[
            {"value": "0", "error_logic": "Неверно сложены дроби."},
            {"value": "2", "error_logic": "Числители и знаменатели сложены неверно."},
        ],
        tags={},
        precomputed_response=SmartVerifyResponse(
            sympy_compatible_string="Integer(1)",
            absolute_correct_answer="1",
        ),
    )

    assert result["tags"]["smart_verify_status"] == "verified_match"


def test_replay_defers_missing_distractors_without_a_model_call(monkeypatch):
    """A local replay cannot silently turn into a distractor-generation run."""
    monkeypatch.setattr(
        "src.pipeline.smart_verify.apply_distractors",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("replay must not generate distractors")
        ),
    )

    result = run_smart_verify_pipeline(
        task_id="REPLAY_DEFER_DISTRACTORS",
        question="Вычислите 1 + 1.",
        correct_answer="2",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
        precomputed_response=SmartVerifyResponse(
            sympy_compatible_string="Integer(2)",
            absolute_correct_answer="2",
        ),
        allow_distractor_generation=False,
    )

    assert result["tags"]["smart_verify_status"] == "verified_match"
    assert result["tags"]["distractor_regen_pending"] is True
    assert result["verification_status"] == "pending"


def test_retry_prompt_explicitly_rejects_boolean_evidence():
    from src.pipeline.smart_verify import _build_compute_prompt

    prompt = _build_compute_prompt(
        "BOOLEAN_RETRY",
        "Вычислите 2 + 2.",
        "exact_number",
        None,
        alt_method=True,
        prior_gate_error="invalid_boolean_result",
    )

    assert "True/False вместо ответа" in prompt
    assert "вычисли и верни сам ответ задачи" in prompt


def test_successful_verify_clears_stale_answer_candidates():
    tags = {
        "answer_gemini_candidate": "20.25",
        "answer_gemini_flash": "20.25",
        "answer_gemini_pro_candidate": "20.25",
        "self_consistency_votes": ["20.25"],
        "self_consistency_majority": True,
        "answer_llm_prose": "243/8",
    }

    clear_stale_verify_flags(tags)

    assert tags == {"answer_llm_prose": "243/8"}


def test_locked_comparison_task_synchronizes_complete_status_from_valid_choices():
    result = run_smart_verify_pipeline(
        task_id="CMP1",
        question="Сравните результаты. Запишите знак: A ... K.",
        correct_answer="<",
        answer_type="exact_number",
        distractor_meta=[
            {
                "value": ">",
                "error_logic": "Ученик перепутал направление сравнения двух значений.",
            },
            {
                "value": "=",
                "error_logic": "Ученик ошибочно решил, что вычисленные значения равны.",
            },
        ],
        tags={
            "smart_verify_status": "verified_match",
            "answer_verify_mode": "verified_match",
            "answer_locked": True,
            "answer_gemini_verified": True,
            "choices_complete": False,
            "distractor_regen_pending": True,
        },
    )

    assert result["verification_status"] == "verified"
    assert result["tags"]["choices_complete"] is True
    assert "distractor_regen_pending" not in result["tags"]


def test_legacy_numeric_type_with_a_semantic_answer_uses_response_route(monkeypatch):
    captured = {}

    def fake_text(**kwargs):
        captured.update(kwargs)
        return {
            "status": "success",
            "correct_answer": "Саша",
            "distractor_meta": [],
            "tags": {"smart_verify_status": "verified_match"},
            "action": "verified_match",
            "verification_status": "pending",
        }

    monkeypatch.setattr("src.pipeline.smart_verify.run_text_verify_pipeline", fake_text)
    result = run_smart_verify_pipeline(
        task_id="LEGACY_TEXT_1",
        question="Кто тяжелее?",
        correct_answer="Саша",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
    )

    assert captured["correct_answer"] == "Саша"
    assert result["correct_answer"] == "Саша"
    assert captured["answer_type"] == "text"
    assert result["tags"]["smart_verify_effective_answer_type"] == "text"
    assert result["tags"]["smart_verify_source_answer_type"] == "exact_number"


def test_legacy_numeric_pair_uses_equation_solution_effective_type(monkeypatch):
    """Source answer_type stays immutable while verification uses its real domain."""
    captured = {}

    def fake_compute(_task_id, _question, atype, _stored, **_kwargs):
        captured["atype"] = atype
        return (
            SmartVerifyResponse(
                sympy_compatible_string="[(3, 1)]",
                absolute_correct_answer="(3; 1)",
            ),
            SimpleNamespace(ok=True, reason="sympy_match", computed_local="(3; 1)"),
            "(3; 1)",
        )

    monkeypatch.setattr("src.pipeline.smart_verify._run_single_compute", fake_compute)
    result = run_smart_verify_pipeline(
        task_id="LEGACY_PAIR_1",
        question="Решите систему уравнений.",
        correct_answer="(3; 1)",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
        allow_distractor_generation=False,
    )

    assert captured["atype"] == "equation_solution"
    assert result["correct_answer"] == "(3; 1)"
    assert result["tags"]["smart_verify_effective_answer_type"] == "equation_solution"
    assert result["tags"]["smart_verify_source_answer_type"] == "exact_number"


def test_response_route_does_not_capture_an_ordinary_numeric_answer_with_units():
    assert not _requires_response_route("exact_number", "$81$ кв. м")
    assert _requires_response_route("exact_number", "да")
    assert _requires_response_route("exact_number", "Ворчун, $11/27$ кг")


def test_response_route_preserves_source_when_independent_answer_disagrees(monkeypatch):
    from src.schemas.smart_verify import TextVerifyResponse

    monkeypatch.setattr(
        "src.pipeline.smart_verify_text._run_text_llm",
        lambda *_args, **_kwargs: TextVerifyResponse(
            absolute_correct_answer="36", confidence="high"
        ),
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text.is_high_confidence_arithmetic",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "src.pipeline.smart_verify_text._compare_text_source_relation",
        lambda **_kwargs: "inconclusive",
    )
    result = run_smart_verify_pipeline(
        task_id="LEGACY_TEXT_SOURCE",
        question="Сколько коробок нужно купить?",
        correct_answer="20 коробок",
        answer_type="exact_number",
        distractor_meta=[],
        tags={},
    )

    assert result["correct_answer"] == "20 коробок"
    assert result["tags"]["smart_verify_status"] == "needs_human_review"
    assert result["tags"]["answer_source_review_required"] is True


def test_pedagogy_prompt_requires_recalculation_to_exact_distractor_value():
    prompt = _build_pedagogy_prompt(
        question="Найдите число",
        correct_answer="37",
        answer_type="exact_number",
        distractors=[
            {
                "value": "47",
                "error_logic": "Получил 73, переставил цифры и получил 47.",
            }
        ],
    )

    assert "пересчитай КАЖДУЮ" in prompt
    assert "перестановка цифр 73 даёт 37, а не 47" in prompt
    assert "reject_value" in prompt
