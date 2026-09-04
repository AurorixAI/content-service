"""Вьюер очереди ручной проверки (Сессия 5)."""

import pytest

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline import scoring as SC
from src.pipeline.models import ExtractedTask
from src.viewer import build as V


def task(num="1", text="Вычислите площадь круга радиуса пять", answer="42",
         source=prov.BOOK_KEY, ctx="", page=7, para="§1"):
    return ExtractedTask(
        exercise_number=num, question_text=text, answer_raw=answer,
        answer_source=source, answer_type="exact_number",
        shared_context=ctx, page=page, paragraph_number=para,
    )


def scored(tasks, verdicts):
    SC.score_tasks(tasks, verdicts)
    return tasks, verdicts


class TestBuildHtml:
    def test_renders_task_content(self):
        t = task()
        html = V.build_html(*scored([t], [G.Verdict()]))
        assert "Вычислите площадь круга" in html
        assert "№1" in html

    def test_katex_delimiters_survive_escaping(self):
        t = task(text=r"Решите $x^2 - 5x + 6 = 0$")
        html = V.build_html(*scored([t], [G.Verdict()]))
        assert "$x^2 - 5x + 6 = 0$" in html, "KaTeX не увидит формулу, если $ съеден"

    def test_html_is_escaped(self):
        t = task(text="<script>alert(1)</script>")
        html = V.build_html(*scored([t], [G.Verdict()]))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_shared_context_shown(self):
        t = task(ctx="В задачах 140–145 решите уравнение:")
        html = V.build_html(*scored([t], [G.Verdict()]))
        assert "В задачах 140–145" in html

    def test_gate_reasons_shown(self):
        v = G.Verdict()
        v.add(G.REVIEW, "не компилируется формул: 1")
        html = V.build_html(*scored([task()], [v]))
        assert "не компилируется формул: 1" in html

    def test_ai_answer_marked_distinctly(self):
        t = task(source=prov.AI_SOLVED)
        html = V.build_html(*scored([t], [G.Verdict()]))
        assert "придуман моделью" in html

    def test_unmeasured_confidence_shows_dash_not_zero(self):
        t = task()
        # компиляция не измерена и формул нет → ocr = None
        html = V.build_html(*scored([t], [G.Verdict(compile_measured=False)]))
        assert "ocr —" in html

    def test_empty_input(self):
        html = V.build_html([], [])
        assert "задач: 0" in html

    def test_mismatched_lengths_rejected(self):
        with pytest.raises(AssertionError):
            V.build_html([task()], [])


class TestQueueOrder:
    def test_worst_first(self):
        clean = task(num="1")
        broken = task(num="2", text="")
        tasks = [clean, broken]
        vs = [G.Verdict(), G.Verdict(status=G.REJECT)]
        html = V.build_html(*scored(tasks, vs))
        assert html.index("№2") < html.index("№1"), "брак обязан быть выше чистого"

    def test_review_count_in_stats(self):
        tasks = [task(num="1"), task(num="2", text="")]
        vs = [G.Verdict(), G.Verdict(status=G.REJECT)]
        html = V.build_html(*scored(tasks, vs))
        assert "на проверку: 1" in html


class TestWriteFile:
    def test_writes_file(self, tmp_path):
        out = tmp_path / "sub" / "viewer.html"
        p = V.build_viewer(*scored([task()], [G.Verdict()]), out)
        assert p.is_file() and p.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
