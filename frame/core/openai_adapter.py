from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import OpenAI, Stream
from openai.types.responses import Response, ResponseStreamEvent

from frame.core.llm_types import (
    InvocationRequest,
    OpenAIInputItem,
    OpenAIToolSpec,
    ParsedResponse,
    ParsedTextChunk,
    ParsedToolCall,
    TextDeltaCallback,
    ToolExecutionRecord,
    ToolCallMode,
)
from frame.core.message import Message

# OpenAI 适配器，负责将中间层的调用请求转换成 OpenAI API 的输入格式，以及将 OpenAI 的响应解析成中间层可以理解的格式
class OpenAIResponsesAdapter:
    """Adapter that isolates OpenAI Responses API payload/parse details."""

    def __init__(self, client: OpenAI, model_id: str):
        self.client_ = client
        self.model_id_ = model_id

    def build_message_input_items(self, messages: List[Message]) -> List[OpenAIInputItem]:
        items: List[OpenAIInputItem] = []
        for msg in messages:
            if msg.type == "tool_response" and hasattr(msg, "call_id"):
                call_id = getattr(msg, "call_id", "")
                if call_id:
                    items.append(
                        OpenAIInputItem(
                            payload={
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": msg.content,
                            }
                        )
                    )
                    continue

            role = msg.role if msg.role in {"system", "user", "assistant"} else "user"
            items.append(OpenAIInputItem(payload={"role": role, "content": msg.content}))
        return items

    # 返回值可用于后续请求的tools参数
    def build_tool_specs(self, request: InvocationRequest) -> List[OpenAIToolSpec]:
        if request.policy.tool_mode == ToolCallMode.OFF:
            return []
        specs = [OpenAIToolSpec(payload=tool.desc().to_openai_tool()) for tool in request.tools]
        return specs

    # 基础逻辑：保证基础字段'model'和'input'的存在，除此之外可以通过额外的参数来扩展，可以支持后续的多模态以及工具等
    def invoke(
        self,
        request: InvocationRequest,
        input_items: List[OpenAIInputItem],
        previous_response_id: Optional[str] = None,     # 可选，配置该字段可以由LLM服务商自己进行上下文管理与关联
    ) -> Response:
        payload: Dict[str, Any] = {
            "model": self.model_id_,
            "input": [item.payload for item in input_items],
        }
        if request.instructions:
            payload["instructions"] = request.instructions

        tool_specs = self.build_tool_specs(request)
        if tool_specs:
            payload["tools"] = [item.payload for item in tool_specs]

        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        return self.client_.responses.create(**payload)

    def invoke_stream(
        self,
        request: InvocationRequest,
        input_items: List[OpenAIInputItem],
        previous_response_id: Optional[str] = None,
    ) -> Stream[ResponseStreamEvent]:
        payload: Dict[str, Any] = {
            "model": self.model_id_,
            "input": [item.payload for item in input_items],
            "stream": True,
        }
        if request.instructions:
            payload["instructions"] = request.instructions

        tool_specs = self.build_tool_specs(request)
        if tool_specs:
            payload["tools"] = [item.payload for item in tool_specs]

        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        return self.client_.responses.create(**payload)

    def parse_response(self, response: Response) -> ParsedResponse:
        parsed = ParsedResponse(response_id=getattr(response, "id", None))
        output_items = getattr(response, "output", None) or [] 
        for item in output_items:
            item_type = getattr(item, "type", None)
            if item_type == "message":
                self._parse_message_item(item, parsed)
            elif item_type == "function_call":
                parsed.tool_calls.append(self._parse_tool_call_item(item))
        return parsed

    def build_function_call_outputs(self, records: List[ToolExecutionRecord]) -> List[OpenAIInputItem]:
        items: List[OpenAIInputItem] = []
        for record in records:
            items.append(
                OpenAIInputItem(
                    payload={
                        "type": "function_call_output",
                        "call_id": record.call.call_id,
                        "output": record.result.model_dump_json(),
                    }
                )
            )
        return items

    def consume_stream(
        self,
        stream: Stream[ResponseStreamEvent],
        on_text_delta: Optional[TextDeltaCallback] = None,
    ) -> ParsedResponse:
        completed_response: Optional[Response] = None
        buffered_text: str = ""
        text_chunks: List[ParsedTextChunk] = []

        for event in stream:
            event_type = getattr(event, "type", None)
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    buffered_text += delta
                    if on_text_delta:
                        on_text_delta(delta)
                continue

            if event_type == "response.output_text.done":
                final_text = getattr(event, "text", None) or buffered_text
                if final_text:
                    text_chunks.append(ParsedTextChunk(text=final_text))
                buffered_text = ""
                continue

            if event_type == "response.completed":
                event_response = getattr(event, "response", None)
                if isinstance(event_response, Response):
                    completed_response = event_response

        if buffered_text:
            text_chunks.append(ParsedTextChunk(text=buffered_text))

        if completed_response is not None:
            parsed = self.parse_response(completed_response)
            if not parsed.texts and text_chunks:
                parsed.texts.extend(text_chunks)
            return parsed

        # 极端情况下拿不到 completed 事件，这里做一个保底返回。
        return ParsedResponse(texts=text_chunks)

    def _parse_message_item(self, item: Any, parsed: ParsedResponse) -> None:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            content_type = getattr(content, "type", None)
            if content_type != "output_text":
                continue
            text = getattr(content, "text", "")
            if text:
                parsed.texts.append(ParsedTextChunk(text=text))

    # 文档中说明type为function_call的output item不可能继续嵌套多个function_call，因此这里不进行递归解析
    def _parse_tool_call_item(self, item: Any) -> ParsedToolCall:
        tool_name = getattr(item, "name", "")
        call_id = getattr(item, "call_id", None) or getattr(item, "id", "")
        arguments_json = getattr(item, "arguments", "{}")

        try:
            loaded = json.loads(arguments_json)
            arguments = loaded if isinstance(loaded, dict) else {}
        except (TypeError, json.JSONDecodeError):
            arguments = {}

        return ParsedToolCall(
            tool_name=tool_name,
            call_id=call_id,
            arguments_json=arguments_json,
            arguments=arguments,
        )