from types import SimpleNamespace

import pytest

from frame.core.config import LLMConfig
from frame.core.llm import LLMClient


class Retryable502Error(Exception):
    def __init__(self, msg: str = "bad gateway"):
        super().__init__(msg)
        self.status_code = 502


class NonRetryable400Error(Exception):
    def __init__(self, msg: str = "bad request"):
        super().__init__(msg)
        self.status_code = 400


class FakeCompletions:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
        if not self.outputs:
            raise AssertionError("missing fake output")
        current = self.outputs.pop(0)
        if isinstance(current, Exception):
            raise current
        return current


class FakeChat:
    def __init__(self, outputs):
        self.completions = FakeCompletions(outputs)


class FakeClient:
    def __init__(self, outputs):
        self.chat = FakeChat(outputs)


def _make_response(text: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
            )
        ]
    )


def _make_config(retry_attempts: int = 3, retry_backoff_seconds: float = 0.01) -> LLMConfig:
    return LLMConfig(
        model_id="demo-model",
        api_key="demo-key",
        base_url="http://localhost",
        timeout=5,
        max_rounds=3,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
    )


def test_invoke_retries_on_transient_502_then_succeeds(monkeypatch):
    monkeypatch.setattr("frame.core.llm.time.sleep", lambda _: None)

    fake_client = FakeClient([
        Retryable502Error(),
        _make_response("ok"),
    ])
    llm = LLMClient(_make_config(retry_attempts=3), client=fake_client)

    out = llm.invoke("hello")
    assert out == "ok"
    assert fake_client.chat.completions.call_count == 2


def test_invoke_non_retryable_fails_fast(monkeypatch):
    monkeypatch.setattr("frame.core.llm.time.sleep", lambda _: None)

    fake_client = FakeClient([NonRetryable400Error()])
    llm = LLMClient(_make_config(retry_attempts=3), client=fake_client)

    with pytest.raises(RuntimeError):
        llm.invoke("hello")

    assert fake_client.chat.completions.call_count == 1


def test_invoke_stops_after_retry_limit(monkeypatch):
    monkeypatch.setattr("frame.core.llm.time.sleep", lambda _: None)

    fake_client = FakeClient([
        Retryable502Error("1"),
        Retryable502Error("2"),
        Retryable502Error("3"),
    ])
    llm = LLMClient(_make_config(retry_attempts=3), client=fake_client)

    with pytest.raises(RuntimeError):
        llm.invoke("hello")

    assert fake_client.chat.completions.call_count == 3
