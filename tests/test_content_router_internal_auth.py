import pytest
from fastapi import HTTPException

from src.api.content_router import require_internal_service_token
from src.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Settings is @lru_cache'd; each test mutates env so the cache must reset."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_rejects_when_secret_is_not_configured_even_with_a_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "")
    with pytest.raises(HTTPException) as exc:
        require_internal_service_token(x_internal_service_token="anything")
    assert exc.value.status_code == 503


def test_rejects_missing_header(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-secret")
    with pytest.raises(HTTPException) as exc:
        require_internal_service_token(x_internal_service_token=None)
    assert exc.value.status_code == 403


def test_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-secret")
    with pytest.raises(HTTPException) as exc:
        require_internal_service_token(x_internal_service_token="wrong-secret")
    assert exc.value.status_code == 403


def test_rejects_empty_string_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-secret")
    with pytest.raises(HTTPException) as exc:
        require_internal_service_token(x_internal_service_token="")
    assert exc.value.status_code == 403


def test_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-secret")
    require_internal_service_token(x_internal_service_token="correct-secret")


def test_rejects_token_that_is_a_prefix_of_the_secret(monkeypatch):
    """Guards against a naive substring/startswith comparison bug."""
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "correct-secret")
    with pytest.raises(HTTPException) as exc:
        require_internal_service_token(x_internal_service_token="correct-secre")
    assert exc.value.status_code == 403
