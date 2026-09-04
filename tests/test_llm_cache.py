"""Кэш ответов модели: успешные — да, отказы — никогда."""

import pytest

from src.pipeline.llm_cache import LLMCache, enabled


@pytest.fixture
def cache(tmp_path):
    return LLMCache(tmp_path / "c.sqlite")


class TestKey:
    def test_same_input_same_key(self, cache):
        a = cache.make_key("m", "prompt", temperature=0.0)
        b = cache.make_key("m", "prompt", temperature=0.0)
        assert a == b

    def test_temperature_changes_key(self, cache):
        # Ответ при 0.0 и при 0.4 — разные ответы, подменять нельзя.
        a = cache.make_key("m", "p", temperature=0.0)
        b = cache.make_key("m", "p", temperature=0.4)
        assert a != b

    def test_model_changes_key(self, cache):
        assert cache.make_key("flash", "p") != cache.make_key("pro", "p")

    def test_prompt_changes_key(self, cache):
        # Правка промпта обязана инвалидировать кэш сама собой.
        assert cache.make_key("m", "p1") != cache.make_key("m", "p2")

    def test_param_order_does_not_matter(self, cache):
        a = cache.make_key("m", "p", temperature=0.0, max_tokens=10)
        b = cache.make_key("m", "p", max_tokens=10, temperature=0.0)
        assert a == b


class TestStore:
    def test_roundtrip(self, cache):
        k = cache.make_key("m", "p")
        cache.set(k, "m", "ответ")
        assert cache.get(k) == "ответ"

    def test_miss_returns_none(self, cache):
        assert cache.get("нет-такого") is None

    def test_empty_response_not_cached(self, cache):
        # Пустой ответ — это отказ, а не результат.
        k = cache.make_key("m", "p")
        cache.set(k, "m", "")
        assert cache.get(k) is None

    def test_overwrite(self, cache):
        k = cache.make_key("m", "p")
        cache.set(k, "m", "первый")
        cache.set(k, "m", "второй")
        assert cache.get(k) == "второй"

    def test_survives_reopen(self, tmp_path):
        path = tmp_path / "c.sqlite"
        c1 = LLMCache(path)
        k = c1.make_key("m", "p")
        c1.set(k, "m", "ответ")
        c1.close()
        assert LLMCache(path).get(k) == "ответ", "кэш обязан переживать перезапуск"

    def test_stats(self, cache):
        cache.set(cache.make_key("m", "p"), "m", "x")
        assert cache.stats()["entries"] == 1


class TestToggle:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_CACHE_ENABLED", raising=False)
        assert enabled()

    def test_disabled_by_env(self, monkeypatch):
        for value in ("false", "0", "no", "OFF"):
            monkeypatch.setenv("LLM_CACHE_ENABLED", value)
            assert not enabled(), value


class _Resp:
    def __init__(self, status=200, text_out="ответ", finish="STOP"):
        self.status_code = status
        self.text = "body"
        self._payload = {
            "candidates": [{
                "finishReason": finish,
                "content": {"parts": [{"text": text_out}]},
            }]
        }

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)


class TestCallGeminiCaching:
    """Поведение на шве: второй такой же вызов не должен идти в сеть."""

    @pytest.fixture(autouse=True)
    def _isolated_cache(self, tmp_path, monkeypatch):
        import src.pipeline.llm_cache as LC

        monkeypatch.setattr(LC, "_CACHE", LLMCache(tmp_path / "c.sqlite"))
        from src.core.config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "gemini_api_key", "AQ.test", raising=False)
        monkeypatch.setattr(s, "vertex_project_id", "", raising=False)

    def test_second_call_served_from_cache(self, monkeypatch):
        import src.pipeline.gemini_client as GC

        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append(url)
            return _Resp(text_out="результат")

        monkeypatch.setattr(GC.requests, "post", fake_post)
        first = GC.call_gemini("промпт", model="m", max_retries=1)
        second = GC.call_gemini("промпт", model="m", max_retries=1)
        assert first == second == "результат"
        assert len(calls) == 1, "второй вызов обязан прийти из кэша"

    def test_failure_is_not_cached(self, monkeypatch):
        import src.pipeline.gemini_client as GC

        state = {"n": 0}

        def flaky_post(url, headers=None, json=None, timeout=None):
            state["n"] += 1
            if state["n"] == 1:
                return _Resp(status=500)
            return _Resp(text_out="успех")

        monkeypatch.setattr(GC.requests, "post", flaky_post)
        monkeypatch.setattr(GC.time, "sleep", lambda *_: None)
        # Первый вызов падает и ретраит внутри — отказ в кэш попасть не должен,
        # иначе повтор после 429 доставал бы из кэша тот же отказ навсегда.
        out = GC.call_gemini("промпт", model="m", max_retries=3)
        assert out == "успех"
        assert state["n"] == 2

    def test_truncated_answer_is_not_cached(self, monkeypatch):
        import src.pipeline.gemini_client as GC

        calls = []

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append(url)
            return _Resp(text_out="обрез", finish="MAX_TOKENS")

        monkeypatch.setattr(GC.requests, "post", fake_post)
        GC.call_gemini("промпт", model="m", max_retries=1)
        GC.call_gemini("промпт", model="m", max_retries=1)
        assert len(calls) == 2, "обрезанный ответ кэшировать нельзя — повтор может дать целый"


class TestCacheUnavailable:
    """Недоступный кэш не должен ронять обращение к модели."""

    def test_unwritable_path_disables_cache_instead_of_raising(self, monkeypatch, tmp_path):
        from src.pipeline import llm_cache

        monkeypatch.setattr(llm_cache, "_CACHE", None)
        monkeypatch.setattr(llm_cache, "_CACHE_DISABLED", False)

        def _boom(*a, **kw):
            raise OSError(30, "Read-only file system: '/app'")

        monkeypatch.setattr(llm_cache, "LLMCache", _boom)
        assert llm_cache.get_cache() is None

    def test_failure_is_remembered(self, monkeypatch):
        from src.pipeline import llm_cache

        monkeypatch.setattr(llm_cache, "_CACHE", None)
        monkeypatch.setattr(llm_cache, "_CACHE_DISABLED", False)
        calls = []

        def _boom(*a, **kw):
            calls.append(1)
            raise OSError(30, "Read-only file system")

        monkeypatch.setattr(llm_cache, "LLMCache", _boom)
        llm_cache.get_cache()
        llm_cache.get_cache()
        llm_cache.get_cache()
        assert len(calls) == 1, "повторные попытки открыть заведомо мёртвый кэш"
