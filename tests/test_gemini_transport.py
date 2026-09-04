"""Выбор транспорта: Vertex+ADC против прямого API-ключа.

`.env.example` документирует ключ как «Option A», но транспорта под него не
было — все точки входа собирали Vertex-URL и требовали ADC-токен.
"""

import pytest

from src.core.config import get_settings
from src.pipeline import gemini_client as GC


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "vertex_project_id", "", raising=False)
    monkeypatch.setattr(s, "gemini_api_key", "", raising=False)
    monkeypatch.setattr(s, "vertex_location", "global", raising=False)
    return s


class TestUseApiKey:
    def test_key_without_project(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "gemini_api_key", "AQ.test", raising=False)
        assert GC.use_api_key()

    def test_project_wins_when_both_set(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "gemini_api_key", "AQ.test", raising=False)
        monkeypatch.setattr(settings, "vertex_project_id", "my-proj", raising=False)
        assert not GC.use_api_key(), "Vertex остаётся приоритетным для прода"

    def test_neither_set(self, settings):
        assert not GC.use_api_key()

    def test_blank_key_is_not_a_key(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "gemini_api_key", "   ", raising=False)
        assert not GC.use_api_key()


class TestEndpoint:
    def test_api_key_endpoint(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "gemini_api_key", "AQ.secret", raising=False)
        url, headers = GC._endpoint("gemini-3.5-flash")
        assert url.startswith("https://generativelanguage.googleapis.com/")
        assert "gemini-3.5-flash:generateContent" in url
        assert headers["x-goog-api-key"] == "AQ.secret"
        assert "Authorization" not in headers, "ключ не требует OAuth-заголовка"

    def test_api_key_never_lands_in_url(self, settings, monkeypatch):
        """B42: ключ в query-строке утекает в текст `HTTPError`, а тот логируется."""
        monkeypatch.setattr(settings, "gemini_api_key", "AQ.secret", raising=False)
        url, _headers = GC._endpoint("gemini-3.5-flash")
        assert "AQ.secret" not in url
        assert "?" not in url and "key=" not in url

    def test_vertex_endpoint_uses_bearer(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "vertex_project_id", "my-proj", raising=False)
        monkeypatch.setattr(GC, "_get_adc_token", lambda: "tok123")
        url, headers = GC._endpoint("gemini-3.5-flash")
        assert "aiplatform.googleapis.com" in url or "my-proj" in url
        assert headers["Authorization"] == "Bearer tok123"

    def test_no_credentials_at_all_raises(self, settings):
        with pytest.raises(RuntimeError, match="VERTEX_PROJECT_ID"):
            GC._endpoint("gemini-3.5-flash")


class TestRefreshAuth:
    def test_api_key_cannot_refresh(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "gemini_api_key", "AQ.secret", raising=False)
        # 401 на ключе означает негодный ключ — ретрай только съест время.
        assert GC._refresh_auth({}) is False

    def test_vertex_refreshes_token(self, settings, monkeypatch):
        monkeypatch.setattr(settings, "vertex_project_id", "my-proj", raising=False)
        monkeypatch.setattr(GC, "_get_adc_token", lambda: "fresh")
        headers = {"Authorization": "Bearer stale"}
        assert GC._refresh_auth(headers) is True
        assert headers["Authorization"] == "Bearer fresh"
