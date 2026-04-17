from __future__ import annotations

from frame.core.base_llm import BaseLLM
from frame.core.config import LLMConfig
from frame.core.llm_types import InvocationResult
from frame.core.message import LLMResponseTextMsg, UserTextMessage
from frame.core.text_emitter import DispatchMode, TextEmitter


def test_text_emitter_per_char_dispatch() -> None:
    received = []

    with TextEmitter(callback=received.append, dispatch_mode=DispatchMode.PER_CHAR, max_queue_size=32) as emitter:
        emitter.emit("hello")
        emitter.emit("!")

    assert "".join(received) == "hello!"


def test_text_emitter_chunk_dispatch() -> None:
    received = []

    with TextEmitter(callback=received.append, dispatch_mode=DispatchMode.CHUNK, max_queue_size=32) as emitter:
        emitter.emit("hello")
        emitter.emit("!")

    assert received == ["hello", "!"]


class _FakeOrchestrator:
    def invoke_streaming(self, request, on_text_delta=None):
        if on_text_delta:
            on_text_delta("ab")
            on_text_delta("cd")
        return InvocationResult(
            emitted_messages=[LLMResponseTextMsg(content="abcd")],
            response_ids=["resp_1"],
            total_tool_rounds=0,
            stopped_reason="completed",
        )


def test_base_llm_streaming_uses_text_emitter_char_dispatch() -> None:
    llm = BaseLLM(
        LLMConfig(
            model_id="test-model",
            organization="",
            api_key="test-key",
            base_url="http://localhost",
            timeout=30,
            max_rounds=1,
        ),
        client=object(),  # type: ignore[arg-type]
    )

    llm.orchestrator_ = _FakeOrchestrator()  # type: ignore[assignment]
    deltas = []

    result = llm.invoke_streaming(
        messages=[UserTextMessage(content="hi")],
        tools=[],
        on_token_callback=deltas.append,
    )

    assert deltas == ["a", "b", "c", "d"]
    assert result is not None
    assert result.content == "abcd"
