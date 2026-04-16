from __future__ import annotations

import time
from typing import Dict, List, Optional

from openai.types.responses import Response

from frame.core.llm_types import (
    InvocationRequest,
    InvocationResult,
    ParsedResponse,
    RetryPolicy,
    ToolExecutionRecord,
    ToolCallMode,
)
from frame.core.logger import Logger, global_logger
from frame.core.message import LLMResponseFunCallMsg, LLMResponseTextMsg, Message, ToolResponseMessage
from frame.core.openai_adapter import OpenAIResponsesAdapter
from frame.tool.base import BaseTool, ToolResponse

# 负责一次调用的状态机编排
class LLMInvocationOrchestrator:
    """Middleware state machine for typed LLM invocation and tool orchestration."""

    def __init__(self, adapter: OpenAIResponsesAdapter, logger: Optional[Logger] = None):
        self.adapter_ = adapter
        self.logger_ = logger or global_logger

    def invoke(self, request: InvocationRequest) -> InvocationResult:
        if request.stream:
            raise ValueError("Streaming mode is not supported by orchestrator.invoke yet")

        result = InvocationResult()
        tool_by_name: Dict[str, BaseTool] = {tool.name: tool for tool in request.tools}

        response = self._invoke_with_retry(
            request=request,
            input_items=self.adapter_.build_message_input_items(request.messages),
            previous_response_id=None,
        )
        parsed = self.adapter_.parse_response(response)
        self._merge_parsed_output(result, parsed)

        # 如果工具调用模式不是自动，则直接返回结果，不进入工具调用和后续追问的循环，由上层控制工具调用的时机和方式
        if request.policy.tool_mode != ToolCallMode.AUTO:
            result.stopped_reason = "completed"
            return result

        rounds = 0
        while parsed.tool_calls and rounds < request.policy.max_tool_rounds:
            rounds += 1
            records = self._execute_tool_calls(parsed, tool_by_name)
            result.tool_execution_records.extend(records)
            self._append_tool_response_messages(result.emitted_messages, records)

            followup_response = self._invoke_with_retry(
                request=request,
                input_items=self.adapter_.build_function_call_outputs(records),
                previous_response_id=parsed.response_id,
            )
            parsed = self.adapter_.parse_response(followup_response)
            self._merge_parsed_output(result, parsed)

        result.total_tool_rounds = rounds
        if parsed.tool_calls and rounds >= request.policy.max_tool_rounds:
            result.stopped_reason = "max_tool_rounds_reached"
        else:
            result.stopped_reason = "completed"

        return result

    def _invoke_with_retry(
        self,
        request: InvocationRequest,
        input_items,
        previous_response_id: Optional[str],
    ) -> Response:
        retry: RetryPolicy = request.policy.retry_policy
        last_error: Optional[Exception] = None

        for attempt in range(1, retry.max_attempts + 1):
            try:
                return self.adapter_.invoke(
                    request=request,
                    input_items=input_items,
                    previous_response_id=previous_response_id,
                )
            except Exception as err:  # pragma: no cover - network exception path
                last_error = err
                self.logger_.warning("LLM invoke failed, attempt=%s err=%s", attempt, str(err))
                if attempt < retry.max_attempts and retry.backoff_seconds > 0:
                    time.sleep(retry.backoff_seconds * attempt)

        if last_error is None:
            raise RuntimeError("LLM invoke failed without explicit exception")
        raise last_error

    # 将解析后的文本和工具调用等信息进行合并，方便后续的分发，result将储存最终的输出结果
    def _merge_parsed_output(self, result: InvocationResult, parsed: ParsedResponse) -> None:
        if parsed.response_id:
            result.response_ids.append(parsed.response_id)

        for chunk in parsed.texts:
            result.emitted_messages.append(LLMResponseTextMsg(content=chunk.text))

        for call in parsed.tool_calls:
            result.emitted_messages.append(
                LLMResponseFunCallMsg.from_raw(
                    tool_name=call.tool_name,
                    call_id=call.call_id,
                    arguments_json=call.arguments_json,
                    arguments=call.arguments,
                )
            )

    """
        tools: 本次请求使用的工具字典
        parsed: LLM返回的解析结果，包含了需要调用的工具信息
    """
    def _execute_tool_calls(self, parsed: ParsedResponse, tools: Dict[str, BaseTool]) -> List[ToolExecutionRecord]:
        records: List[ToolExecutionRecord] = []
        for call in parsed.tool_calls:
            tool = tools.get(call.tool_name)
            if tool is None:
                tool_result = ToolResponse(
                    tool_name=call.tool_name,
                    status="error",
                    output=f"Tool '{call.tool_name}' not found",
                )
            else:
                tool_result = tool.execute(call.arguments)
            records.append(ToolExecutionRecord(call=call, result=tool_result))
        return records

    def _append_tool_response_messages(self, output: List[Message], records: List[ToolExecutionRecord]) -> None:
        for record in records:
            output.append(
                ToolResponseMessage.from_tool_result(
                    tool_name=record.call.tool_name,
                    call_id=record.call.call_id,
                    status=record.result.status,
                    output=record.result.output,
                )
            )