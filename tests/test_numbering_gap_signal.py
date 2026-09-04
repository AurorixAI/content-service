"""B43: сигнал повреждённой сегментации был мёртв дважды.

`scoring.score_structure` понижает доверие по флагу `numbering_gap`, а
`needs_review` отправляет такую задачу в очередь ручной проверки. Работать это
не могло по двум независимым причинам:

1. **Затирание.** `gates.apply_verdicts` делал `task.review_flags = list(v.reasons)`
   — присваивание, а не дополнение. Следующей же строкой `_write_tasks` зовёт
   `scoring.score_tasks`, который читает флаги оттуда. Заодно терялись
   `merged_across_pages` из структурного слоя и флаги из `prototype_ingest`.
2. **Отсутствие производителя.** Флаг `numbering_gap` в `src/` не выставлял
   никто: одноимённая метрика в `src/eval/metrics.py` считает пропуски по
   дампу постфактум и в задачу ничего не пишет.

Тесты держат оба конца: чинить один без другого бессмысленно.
"""

from src.pipeline import gates as G
from src.pipeline import provenance as prov
from src.pipeline import scoring as SC
from src.pipeline import structure as S
from src.pipeline.models import ExtractedTask


def task(number="1", paragraph="7", text="Вычислите площадь круга радиуса пять"):
    return ExtractedTask(
        exercise_number=number, paragraph_number=paragraph,
        question_text=text, answer_raw="42",
        answer_source=prov.BOOK_KEY, answer_type="exact_number",
    )


# ---------------------------------------------------------------------------
# Конец 1: флаги переживают гейты
# ---------------------------------------------------------------------------


class TestFlagsSurviveApplyVerdicts:
    def test_earlier_flag_is_kept(self):
        t = task()
        t.review_flags = [SC.NUMBERING_GAP_FLAG]
        G.apply_verdicts([t], G.evaluate_batch([t], compile_formulas=False))
        assert SC.NUMBERING_GAP_FLAG in t.review_flags

    def test_structure_layer_flag_is_kept(self):
        t = task()
        t.review_flags = ["merged_across_pages"]
        G.apply_verdicts([t], G.evaluate_batch([t], compile_formulas=False))
        assert "merged_across_pages" in t.review_flags

    def test_gate_reasons_are_still_recorded(self):
        t = task(text="Реши")
        t.review_flags = ["merged_across_pages"]
        vs = G.evaluate_batch([t], compile_formulas=False)
        G.apply_verdicts([t], vs)
        assert set(vs[0].reasons) <= set(t.review_flags)
        assert "merged_across_pages" in t.review_flags

    def test_repeated_application_does_not_duplicate(self):
        t = task(text="Реши")
        for _ in range(3):
            G.apply_verdicts([t], G.evaluate_batch([t], compile_formulas=False))
        assert len(t.review_flags) == len(set(t.review_flags))

    def test_summary_still_counts_every_task(self):
        tasks = [task(), task(text="Реши")]
        summary = G.apply_verdicts(tasks, G.evaluate_batch(tasks, compile_formulas=False))
        assert sum(summary.values()) == 2


# ---------------------------------------------------------------------------
# Конец 2: флаг вообще кто-то выставляет
# ---------------------------------------------------------------------------


class TestNumberingGapProducer:
    def test_gap_flags_the_task_before_the_hole(self):
        tasks = [task(number=n) for n in ("70", "72", "73")]
        assert S.flag_numbering_gaps(tasks) == 1
        assert tasks[0].review_flags == [SC.NUMBERING_GAP_FLAG]
        assert tasks[1].review_flags == []

    def test_continuous_numbering_is_clean(self):
        tasks = [task(number=str(n)) for n in range(1, 20)]
        assert S.flag_numbering_gaps(tasks) == 0
        assert all(not t.review_flags for t in tasks)

    def test_two_column_layout_is_not_a_gap(self):
        # Вёрстка в две колонки читается 1,4,2,5,3,6 — порядок не разрыв.
        tasks = [task(number=n) for n in ("1", "4", "2", "5", "3", "6")]
        assert S.flag_numbering_gaps(tasks) == 0

    def test_paragraph_boundaries_are_not_holes(self):
        # §7 кончается на 73, §8 начинается с 1 — это не пропуск 74…
        tasks = [task(number="72", paragraph="7"), task(number="73", paragraph="7"),
                 task(number="1", paragraph="8"), task(number="2", paragraph="8")]
        assert S.flag_numbering_gaps(tasks) == 0

    def test_gap_does_not_cross_paragraphs(self):
        tasks = [task(number="1", paragraph="7"), task(number="9", paragraph="8")]
        # В каждом параграфе по одному номеру — сравнивать не с чем.
        assert S.flag_numbering_gaps(tasks) == 0

    def test_subparts_share_one_number(self):
        tasks = [task(number="43.а"), task(number="43.б"), task(number="44")]
        assert S.flag_numbering_gaps(tasks) == 0

    def test_flag_is_not_duplicated_on_rerun(self):
        tasks = [task(number=n) for n in ("70", "72")]
        S.flag_numbering_gaps(tasks)
        S.flag_numbering_gaps(tasks)
        assert tasks[0].review_flags == [SC.NUMBERING_GAP_FLAG]

    def test_apply_reports_gaps(self):
        tasks = [task(number=n) for n in ("70", "72", "73")]
        _out, summary = S.apply(tasks)
        assert summary["numbering_gaps"] == 1

    def test_flag_string_matches_its_consumer(self):
        assert S.NUMBERING_GAP_FLAG == SC.NUMBERING_GAP_FLAG


# ---------------------------------------------------------------------------
# Оба конца вместе: сигнал доходит до очереди
# ---------------------------------------------------------------------------


class TestSignalReachesTheReviewQueue:
    def test_gap_lowers_structure_and_queues_the_task(self):
        """Воспроизведение дефекта целиком: структура 1.0 вместо 0.5 и мимо очереди."""
        tasks = [task(number=n) for n in ("70", "72", "73")]
        S.flag_numbering_gaps(tasks)

        verdicts = G.evaluate_batch(tasks, compile_formulas=False)
        G.apply_verdicts(tasks, verdicts)
        report = SC.score_tasks(tasks, verdicts)

        assert tasks[0].confidence["structure"] == 0.5
        assert tasks[1].confidence["structure"] == 1.0
        assert report["n_needs_review"] == 1
        assert SC.review_queue(tasks, verdicts)[0] is tasks[0]
