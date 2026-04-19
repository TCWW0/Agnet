"""覆盖中间层编排逻辑（不依赖真实网络调用）。"""

from frame.core.llm_orchestrator import LLMInvocationOrchestrator
from frame.core.llm_types import (
    InvocationPolicy,
    InvocationRequest,
    ParsedResponse,
    ParsedTextChunk,
    ParsedToolCall,
    RetryPolicy,
    ToolCallMode,
)
from frame.core.message import LLMResponseTextMsg, UserTextMessage
from frame.tool.builtin.calculater import CalculaterTool


class _FakeAdapter:
    def __init__(self):
        self.invoke_count = 0
        self.stream_invoke_count = 0

    def build_message_input_items(self, messages):
        return []

    def build_function_call_outputs(self, records):
        return []

    def invoke(self, request, input_items, previous_response_id=None):
        self.invoke_count += 1
        return object()

    def invoke_stream(self, request, input_items, previous_response_id=None):
        self.stream_invoke_count += 1
        return object()

    def consume_stream(self, stream, on_text_delta=None, on_tool_call=None):
        if self.stream_invoke_count == 1:
            return ParsedResponse(
                response_id="resp_1",
                tool_calls=[
                    ParsedToolCall(
                        tool_name="calculater",
                        call_id="call_1",
                        arguments_json='{"operand1":"1", "operand2":"2", "operator":"+"}',
                        arguments={"operand1": "1", "operand2": "2", "operator": "+"},
                    )
                ],
            )

        if on_text_delta:
            on_text_delta("1 + 2 的")
            on_text_delta("结果为 3")
        return ParsedResponse(
            response_id="resp_2",
            texts=[ParsedTextChunk(text="1 + 2 的结果为 3")],
        )

    def parse_response(self, response):
        if self.invoke_count == 1:
            return ParsedResponse(
                response_id="resp_1",
                tool_calls=[
                    ParsedToolCall(
                        tool_name="calculater",
                        call_id="call_1",
                        arguments_json='{"operand1":"1", "operand2":"2", "operator":"+"}',
                        arguments={"operand1": "1", "operand2": "2", "operator": "+"},
                    )
                ],
            )
        return ParsedResponse(
            response_id="resp_2",
            texts=[ParsedTextChunk(text="1 + 2 的结果为 3")],
        )


def test_orchestrator_auto_tool_flow() -> None:
    adapter = _FakeAdapter()
    orchestrator = LLMInvocationOrchestrator(adapter=adapter) # type: ignore

    request = InvocationRequest(
        messages=[UserTextMessage(content="帮我计算 1+2")],
        tools=[CalculaterTool()],
        policy=InvocationPolicy(
            tool_mode=ToolCallMode.AUTO,
            max_tool_rounds=2,
            retry_policy=RetryPolicy(max_attempts=1),
        ),
    )

    result = orchestrator.invoke(request)

    assert result.total_tool_rounds == 1
    assert result.stopped_reason == "completed"
    assert len(result.tool_execution_records) == 1
    assert result.tool_execution_records[0].result.status == "success"
    assert any(isinstance(msg, LLMResponseTextMsg) for msg in result.emitted_messages)


def test_orchestrator_manual_mode_no_tool_execution() -> None:
    adapter = _FakeAdapter()
    orchestrator = LLMInvocationOrchestrator(adapter=adapter) # type: ignore

    request = InvocationRequest(
        messages=[UserTextMessage(content="帮我计算 1+2")],
        tools=[CalculaterTool()],
        policy=InvocationPolicy(
            tool_mode=ToolCallMode.MANUAL,
            max_tool_rounds=2,
            retry_policy=RetryPolicy(max_attempts=1),
        ),
    )

    result = orchestrator.invoke(request)

    assert result.total_tool_rounds == 0
    assert len(result.tool_execution_records) == 0
    assert result.stopped_reason == "completed"


def test_orchestrator_stream_auto_tool_flow() -> None:
    adapter = _FakeAdapter()
    orchestrator = LLMInvocationOrchestrator(adapter=adapter) # type: ignore
    deltas = []

    request = InvocationRequest(
        messages=[UserTextMessage(content="帮我计算 1+2")],
        tools=[CalculaterTool()],
        stream=True,
        policy=InvocationPolicy(
            tool_mode=ToolCallMode.AUTO,
            max_tool_rounds=2,
            retry_policy=RetryPolicy(max_attempts=1),
        ),
    )

    result = orchestrator.invoke_streaming(request=request, on_text_delta=deltas.append)

    assert result.total_tool_rounds == 1
    assert result.stopped_reason == "completed"
    assert len(result.tool_execution_records) == 1
    assert "".join(deltas) == "1 + 2 的结果为 3"
    assert any(isinstance(msg, LLMResponseTextMsg) for msg in result.emitted_messages)
