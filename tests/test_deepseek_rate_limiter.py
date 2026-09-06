"""Global DeepSeek limiter covers worker calls and HTTP retries."""
from __future__ import annotations

from src.pipeline import deepseek_client as client


def test_process_wide_limiter_evenly_paces_all_worker_slots(monkeypatch):
    clock = {"now": 0.0}
    sleeps: list[float] = []

    monkeypatch.setattr(client.time, "monotonic", lambda: clock["now"])

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(client.time, "sleep", fake_sleep)
    limiter = client._GlobalRequestLimiter(60)

    limiter.acquire()
    limiter.acquire()

    assert sleeps == [1.0]
    assert limiter.stats()["request_attempts"] == 2


def test_http_retry_consumes_a_new_global_slot(monkeypatch):
    class Response:
        def __init__(self, status_code: int):
            self.status_code = status_code
            self.text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class Session:
        def __init__(self):
            self.responses = [Response(429), Response(200)]

        def post(self, *_args, **_kwargs):
            return self.responses.pop(0)

    limiter = client._GlobalRequestLimiter(250)
    monkeypatch.setattr(client, "_global_request_limiter", limiter)
    monkeypatch.setattr(client, "_get_session", lambda: Session())
    monkeypatch.setattr(client.time, "sleep", lambda _seconds: None)

    result = client._post_with_retry("https://example.invalid", {}, {}, max_retries=2)

    assert result["choices"][0]["message"]["content"] == "ok"
    assert limiter.stats()["request_attempts"] == 2
    assert limiter.stats()["responses_429"] == 1
