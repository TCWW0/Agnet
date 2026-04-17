from __future__ import annotations

from typing import Any

from frame.core.openai_adapter import OpenAIResponsesAdapter


class _Object:
    def __init__(self, **kwargs: Any):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _build_adapter() -> OpenAIResponsesAdapter:
    return OpenAIResponsesAdapter(client=object(), model_id="test-model")  # type: ignore[arg-type]


def test_consume_stream_parses_tool_call_from_delta_done_events() -> None:
    adapter = _build_adapter()
    deltas = []
    tool_calls = []

    stream = [
        _Object(type="response.output_text.delta", delta="调用工具中"),
        _Object(type="response.output_text.done"),
        _Object(type="response.function_call.delta", id="call_1", name="calculater", delta='{"operand1":"12",'),
        _Object(type="response.function_call.delta", id="call_1", delta='"operand2":"4","operator":"*"}'),
        _Object(type="response.function_call.done", id="call_1"),
    ]

    parsed = adapter.consume_stream(stream, on_text_delta=deltas.append, on_tool_call=tool_calls.append)  # type: ignore[arg-type]

    assert "".join(deltas) == "调用工具中"
    assert len(parsed.texts) == 1
    assert parsed.texts[0].text == "调用工具中"

    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].tool_name == "calculater"
    assert parsed.tool_calls[0].call_id == "call_1"
    assert parsed.tool_calls[0].arguments.get("operand1") == "12"
    assert parsed.tool_calls[0].arguments.get("operand2") == "4"
    assert parsed.tool_calls[0].arguments.get("operator") == "*"

    assert len(tool_calls) == 1
    assert tool_calls[0].call_id == "call_1"


def test_consume_stream_deduplicates_tool_calls_from_completed_response() -> None:
    adapter = _build_adapter()

    completed_response = _Object(
        id="resp_1",
        output=[
            _Object(
                type="function_call",
                name="calculater",
                call_id="call_1",
                arguments='{"operand1":"12","operand2":"4","operator":"*"}',
            ),
            _Object(
                type="message",
                content=[_Object(type="output_text", text="答案是 48")],
            ),
        ],
    )

    stream = [
        _Object(type="response.function_call.delta", id="call_1", name="calculater", delta='{"operand1":"12",'),
        _Object(type="response.function_call.delta", id="call_1", delta='"operand2":"4","operator":"*"}'),
        _Object(type="response.function_call.done", id="call_1"),
        _Object(type="response.completed", response=completed_response),
    ]

    parsed = adapter.consume_stream(stream)  # type: ignore[arg-type]

    assert parsed.response_id == "resp_1"
    assert len(parsed.texts) == 1
    assert parsed.texts[0].text == "答案是 48"
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].call_id == "call_1"


def test_consume_stream_flushes_pending_tool_buffer_on_error() -> None:
    adapter = _build_adapter()

    stream = [
        _Object(type="response.function_call.delta", id="call_err", name="calculater", delta='{"operand1":"9"'),
        _Object(type="response.error", error={"message": "stream failed"}),
    ]

    parsed = adapter.consume_stream(stream)  # type: ignore[arg-type]

    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].call_id == "call_err"
    assert parsed.tool_calls[0].tool_name == "calculater"
    assert parsed.tool_calls[0].arguments == {}
