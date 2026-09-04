"""Учёт расхода токенов: «не измерено» ≠ «ноль»."""

import pytest

from src.pipeline.usage import ModelUsage, UsageTracker, estimate_cost


@pytest.fixture
def tracker():
    return UsageTracker()


_MD = {"promptTokenCount": 100, "candidatesTokenCount": 20, "thoughtsTokenCount": 5}


class TestRecord:
    def test_single_call(self, tracker):
        tracker.record("flash", _MD)
        u = tracker.snapshot()["flash"]
        assert u["calls"] == 1
        assert u["prompt_tokens"] == 100
        assert u["output_tokens"] == 20
        assert u["thinking_tokens"] == 5
        assert u["total_tokens"] == 125

    def test_accumulates(self, tracker):
        tracker.record("flash", _MD)
        tracker.record("flash", _MD)
        assert tracker.snapshot()["flash"]["prompt_tokens"] == 200

    def test_models_kept_apart(self, tracker):
        tracker.record("flash", _MD)
        tracker.record("pro", _MD)
        assert set(tracker.snapshot()) == {"flash", "pro"}

    def test_missing_metadata_counts_call_only(self, tracker):
        # Ответ без usageMetadata: вызов был, токены неизвестны.
        tracker.record("flash", None)
        u = tracker.snapshot()["flash"]
        assert u["calls"] == 1 and u["total_tokens"] == 0

    def test_cache_hit_is_free(self, tracker):
        tracker.record_cache_hit("flash")
        u = tracker.snapshot()["flash"]
        assert u["cached_calls"] == 1
        assert u["calls"] == 0, "попадание в кэш — не вызов модели"
        assert u["total_tokens"] == 0


class TestTotals:
    def test_sums_across_models(self, tracker):
        tracker.record("flash", _MD)
        tracker.record("pro", _MD)
        assert tracker.totals().total_tokens == 250

    def test_empty(self, tracker):
        assert tracker.totals().total_tokens == 0

    def test_reset(self, tracker):
        tracker.record("flash", _MD)
        tracker.reset()
        assert tracker.snapshot() == {}


class TestCost:
    def test_thinking_billed_as_output(self):
        u = ModelUsage(prompt_tokens=1_000_000, output_tokens=500_000,
                       thinking_tokens=500_000)
        # вход 1$/1M, выход 10$/1M → 1 + (0.5+0.5)*10 = 11
        assert estimate_cost(u, input_per_1m=1.0, output_per_1m=10.0) == 11.0

    def test_zero_usage_is_free(self):
        assert estimate_cost(ModelUsage(), input_per_1m=5.0, output_per_1m=5.0) == 0.0

    def test_batch_discount_is_caller_choice(self):
        # Цены параметром: тариф Batch вдвое дешевле, и это решает вызывающий.
        u = ModelUsage(prompt_tokens=1_000_000)
        full = estimate_cost(u, input_per_1m=2.0, output_per_1m=2.0)
        batch = estimate_cost(u, input_per_1m=1.0, output_per_1m=1.0)
        assert batch == full / 2


class TestReport:
    def test_empty_report(self, tracker):
        assert "вызовов не было" in tracker.format_report()

    def test_report_mentions_model_and_cache(self, tracker):
        tracker.record("gemini-3.5-flash", _MD)
        tracker.record_cache_hit("gemini-3.5-flash")
        out = tracker.format_report()
        assert "gemini-3.5-flash" in out
        assert "из кэша 1" in out
        assert "ИТОГО" in out
