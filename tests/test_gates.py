"""Гейты на шве записи: три независимых сигнала и вердикт."""

import pytest

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask


def task(text="Вычислите площадь круга радиуса пять", latex="", answer="42",
         source=prov.BOOK_KEY, atype="exact_number"):
    return ExtractedTask(
        question_text=text, question_latex=latex, answer_raw=answer,
        answer_source=source, answer_type=atype,
    )


class TestExtractFormulas:
    def test_inline_and_display(self):
        got = G.extract_formulas(r"текст $a+b$ и $$c+d$$")
        assert got == ["a+b", "c+d"]

    def test_latex_delimiters(self):
        got = G.extract_formulas(r"\(x\) и \[y\]")
        assert got == ["x", "y"]

    def test_empty_sources(self):
        assert G.extract_formulas("", None) == []

    def test_multiline_display(self):
        assert G.extract_formulas("$$a\n+ b$$") == ["a\n+ b"]


class TestVerdictLattice:
    def test_reject_wins_over_review(self):
        v = G.Verdict()
        v.add(G.REVIEW, "раз")
        v.add(G.REJECT, "два")
        assert v.status == G.REJECT

    def test_review_does_not_undo_reject(self):
        v = G.Verdict()
        v.add(G.REJECT, "раз")
        v.add(G.REVIEW, "два")
        assert v.status == G.REJECT

    def test_reasons_accumulate(self):
        v = G.Verdict()
        v.add(G.REVIEW, "раз")
        v.add(G.REVIEW, "два")
        assert v.reasons == ["раз", "два"]

    def test_clean_verdict_is_pass(self):
        assert G.Verdict().ok


class TestStructure:
    def test_empty_statement_rejected(self):
        v = G.Verdict()
        G.check_structure(task(text=""), v)
        assert v.status == G.REJECT

    def test_fragment_rejected(self):
        v = G.Verdict()
        G.check_structure(task(text="Реши"), v)
        assert v.status == G.REJECT

    def test_missing_answer_is_review_not_reject(self):
        """Нет ответа — чинится, значит карантин, а не отказ."""
        v = G.Verdict()
        G.check_structure(task(answer=""), v)
        assert v.status == G.REVIEW

    def test_text_type_may_have_no_answer(self):
        v = G.Verdict()
        G.check_structure(task(answer="", atype="open_text"), v)
        assert v.ok


class TestProvenanceGate:
    def test_ai_answer_needs_human(self):
        """И2 в форме гейта: придуманное не попадает в банк само."""
        v = G.Verdict()
        G.check_provenance(task(source=prov.AI_SOLVED), v)
        assert v.status == G.REVIEW

    def test_book_answer_passes(self):
        v = G.Verdict()
        G.check_provenance(task(source=prov.BOOK_KEY), v)
        assert v.ok

    def test_sympy_derived_passes(self):
        v = G.Verdict()
        G.check_provenance(task(source=prov.SYMPY_DERIVED), v)
        assert v.ok


class TestArtifactGate:
    def test_lost_backslash_caught(self):
        v = G.Verdict()
        G.check_artifacts(task(latex=r"$rac{1}{2}$"), v)
        assert v.status == G.REVIEW
        assert v.artifacts

    def test_clean_latex_passes(self):
        v = G.Verdict()
        G.check_artifacts(task(latex=r"$\frac{1}{2}$"), v)
        assert v.ok

    def test_artifacts_found_in_answer_too(self):
        v = G.Verdict()
        G.check_artifacts(task(answer=r"$150^\\circ$"), v)
        assert v.status == G.REVIEW


class TestBatch:
    def test_no_compile_marks_unmeasured(self):
        """Не измеряли ≠ измерили и ноль."""
        vs = G.evaluate_batch([task()], compile_formulas=False)
        assert vs[0].compile_measured is False

    def test_summary_counts_every_task(self):
        tasks = [task(), task(text="Реши"), task(source=prov.AI_SOLVED)]
        vs = G.evaluate_batch(tasks, compile_formulas=False)
        summary = G.apply_verdicts(tasks, vs)
        assert sum(summary.values()) == 3

    def test_reasons_land_on_the_task(self):
        tasks = [task(text="Реши")]
        vs = G.evaluate_batch(tasks, compile_formulas=False)
        G.apply_verdicts(tasks, vs)
        assert tasks[0].review_flags

    def test_empty_batch(self):
        assert G.evaluate_batch([]) == []

    def test_verdict_per_task_preserved_in_order(self):
        tasks = [task(), task(text="Реши"), task()]
        vs = G.evaluate_batch(tasks, compile_formulas=False)
        assert [v.status for v in vs] == [G.PASS, G.REJECT, G.PASS]


class TestCompileGate:
    """KaTeX доступен не везде — эти тесты пропускаются без Node."""

    @pytest.fixture(autouse=True)
    def _need_katex(self):
        from src.validate import katex
        if not katex.is_available():
            pytest.skip("нет Node/katex")

    def test_broken_formula_goes_to_review(self):
        tasks = [task(latex=r"$\frac{1}{2$")]
        vs = G.evaluate_batch(tasks)
        assert vs[0].status == G.REVIEW
        assert vs[0].formulas_broken == 1

    def test_valid_formula_passes(self):
        tasks = [task(latex=r"$\frac{1}{2}$")]
        vs = G.evaluate_batch(tasks)
        assert vs[0].ok
        assert vs[0].formulas_checked == 1

    def test_compiling_garbage_still_caught_by_lexical_detector(self):
        """Замер С2: артефактов больше, чем непроходящих компиляцию.

        `rac{1}{2}` компилируется без ошибки и показывает ученику мусор —
        один сигнал качества структурно недостаточен.
        """
        tasks = [task(latex=r"$rac{1}{2}$")]
        vs = G.evaluate_batch(tasks)
        assert vs[0].formulas_broken == 0     # компиляции не за что зацепиться
        assert vs[0].artifacts                 # лексика поймала
        assert vs[0].status == G.REVIEW

    def test_formulas_attributed_to_the_right_task(self):
        tasks = [task(latex=r"$\frac{1}{2}$"), task(latex=r"$\frac{1}{2$"), task()]
        vs = G.evaluate_batch(tasks)
        assert vs[0].formulas_broken == 0
        assert vs[1].formulas_broken == 1
        assert vs[2].formulas_checked == 0


class TestB1EmptyStatementWithSubparts:
    """B1: «1. а) … б) …» — законный формат книги, а не пустая задача."""

    def test_empty_statement_without_subparts_rejected(self):
        t = task(text="")
        v = G.Verdict()
        G.check_structure(t, v)
        assert v.status == G.REJECT

    def test_empty_statement_with_subparts_not_rejected(self):
        t = task(text="")
        t.answer_options = ["а) Ученик обточил 120 деталей", "б) Токарь — на 36 больше"]
        v = G.Verdict()
        G.check_structure(t, v)
        assert v.status != G.REJECT

    def test_short_statement_with_subparts_not_rejected(self):
        t = task(text="Задача 1.")
        t.answer_options = ["а) первый пункт", "б) второй пункт"]
        v = G.Verdict()
        G.check_structure(t, v)
        assert v.status != G.REJECT

    def test_short_statement_without_subparts_still_rejected(self):
        v = G.Verdict()
        G.check_structure(task(text="Реши"), v)
        assert v.status == G.REJECT


class TestPromotionSkillGuards:
    """Заслоны промоушена: демо-навык и схлопывание классификации."""

    def test_demo_prefix_recognised(self):
        from src.pipeline.staging import _DEMO_SKILL_PREFIX

        assert "DEMO_S01_01_01".startswith(_DEMO_SKILL_PREFIX)
        assert not "G5_S01_01_01".startswith(_DEMO_SKILL_PREFIX)

    def test_collapse_threshold_is_set(self):
        from src.pipeline.staging import _COLLAPSE_MIN_TASKS

        # Короткий прогон может законно лечь в один навык — порог нужен.
        assert _COLLAPSE_MIN_TASKS >= 10

    def test_report_carries_new_fields(self):
        from src.pipeline.staging import PromotionReport

        d = PromotionReport().as_dict()
        assert "blocked_demo_skill" in d
        assert "skill_collapse" in d
