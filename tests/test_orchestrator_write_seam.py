"""Шов записи: конвейер уходит в staging через гейты, а не в tasks_master.

Инвариант И3 держится ровно здесь. До этого шва гейты существовали, но
стояли в стороне от пути записи, и вердикт ни на что не влиял.
"""

import pytest

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline.models import ExtractedTask
from src.pipeline.orchestrator import DigitizationOrchestrator


def task(text="Вычислите площадь круга радиуса пять", answer="42"):
    return ExtractedTask(
        question_text=text, answer_raw=answer,
        answer_source=prov.BOOK_KEY, answer_type="exact_number",
    )


class _FakeStaging:
    def __init__(self):
        self.calls = []

    def write_batch(self, tasks, verdicts, *, textbook_id, class_level, run_id, prefix):
        self.calls.append({
            "tasks": list(tasks), "verdicts": list(verdicts),
            "textbook_id": textbook_id, "class_level": class_level,
            "run_id": run_id, "prefix": prefix,
        })
        return len(tasks)


class _FakeMaster:
    def __init__(self):
        self.calls = []

    def write_batch(self, tasks, textbook_id, class_level, prefix="G_TB"):
        self.calls.append(list(tasks))
        return len(tasks)


@pytest.fixture
def orch(monkeypatch):
    """Оркестратор без Redis/БД — нужен только шов записи."""
    monkeypatch.setattr("src.pipeline.orchestrator.JobStateManager", lambda: object())
    monkeypatch.setattr("src.pipeline.orchestrator.DBWriter", _FakeMaster)
    monkeypatch.setattr("src.pipeline.orchestrator.StagingWriter", _FakeStaging)
    o = DigitizationOrchestrator(job_id="j1", textbook_id="tb1", class_level=8)
    return o


class TestWriteTarget:
    def test_default_goes_to_staging(self, orch):
        assert orch._write_tasks([task(), task()]) == 2
        assert len(orch.staging.calls) == 1
        assert orch.writer.calls == []  # в tasks_master не писал никто

    def test_verdict_accompanies_every_task(self, orch):
        orch._write_tasks([task(), task(), task()])
        call = orch.staging.calls[0]
        assert len(call["verdicts"]) == len(call["tasks"]) == 3
        assert all(isinstance(v, G.Verdict) for v in call["verdicts"])

    def test_run_id_is_stable_across_batches(self, orch):
        orch._write_tasks([task()])
        orch._write_tasks([task()])
        run_ids = {c["run_id"] for c in orch.staging.calls}
        assert run_ids == {orch.run_id}, "один прогон — один run_id"

    def test_reject_is_written_not_dropped(self, orch):
        # Пустое условие — структурный reject. Брак обязан попасть в карантин,
        # иначе он теряется молча.
        orch._write_tasks([task(text="")])
        call = orch.staging.calls[0]
        assert len(call["tasks"]) == 1
        assert call["verdicts"][0].status == G.REJECT

    def test_verdict_reasons_land_on_task(self, orch):
        bad = task(text="")
        orch._write_tasks([bad])
        assert bad.review_flags, "причины вердикта должны осесть в review_flags"

    def test_empty_batch_writes_nothing(self, orch):
        assert orch._write_tasks([]) == 0
        assert orch.staging.calls == []

    def test_master_target_is_emergency_fallback(self, orch, monkeypatch):
        from src.core.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "pipeline_write_target", "master", raising=False)
        monkeypatch.setattr("src.pipeline.orchestrator.get_settings", lambda: s)
        assert orch._write_tasks([task()]) == 1
        assert len(orch.writer.calls) == 1
        assert orch.staging.calls == [], "в аварийном режиме staging не трогаем"


class TestExtractionProvenance:
    """И1 на шве извлечения: ответ модели не должен выглядеть как книжный."""

    def test_extraction_answer_marked_ai_solved(self, orch):
        t = task(answer="215")
        t.answer_source = prov.ABSENT
        orch._mark_extraction_provenance([t])
        assert t.answer_source == prov.AI_SOLVED

    def test_empty_answer_stays_absent(self, orch):
        t = task(answer="")
        t.answer_source = prov.ABSENT
        orch._mark_extraction_provenance([t])
        assert t.answer_source == prov.ABSENT

    def test_existing_source_not_downgraded(self, orch):
        t = task(answer="215")
        t.answer_source = prov.BOOK_KEY
        orch._mark_extraction_provenance([t])
        assert t.answer_source == prov.BOOK_KEY

    def test_placeholder_dash_is_not_an_answer(self, orch):
        t = task(answer="—")
        t.answer_source = prov.ABSENT
        orch._mark_extraction_provenance([t])
        assert t.answer_source == prov.ABSENT


class TestScoringOnSeam:
    """Скоринг стоит на том же шве: без него confidence уезжает пустым."""

    def test_confidence_filled_before_staging(self, orch):
        t = task()
        orch._write_tasks([t])
        assert set(t.confidence) == {"ocr", "structure", "answer"}

    def test_confidence_reaches_staging_writer(self, orch):
        orch._write_tasks([task(), task()])
        written = orch.staging.calls[0]["tasks"]
        assert all(w.confidence for w in written), "staging должен получить непустой confidence"

    def test_scoring_does_not_change_verdict(self, orch):
        t = task()
        orch._write_tasks([t])
        assert orch.staging.calls[0]["verdicts"][0].status == G.PASS
