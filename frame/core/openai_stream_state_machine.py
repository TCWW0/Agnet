from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Set, cast

from pydantic import BaseModel, ConfigDict, Field

from frame.core.llm_types import ParsedTextChunk, ParsedToolCall, TextDeltaCallback, ToolCallCallback


class ToolCallBuffer(BaseModel):
    """Accumulate one tool-call argument stream by call id."""

    call_id: str
    tool_name: str = ""
    arguments_json: str = ""


class StreamConsumeState(BaseModel):
    """Mutable state used by streaming consumer state machine."""

    text_buffer: str = ""
    text_chunks: List[ParsedTextChunk] = Field(default_factory=list)

    tool_buffers: Dict[str, ToolCallBuffer] = Field(default_factory=dict)
    tool_calls: List[ParsedToolCall] = Field(default_factory=list)
    seen_tool_call_ids: Set[str] = Field(default_factory=set)

    completed_response: Optional[Any] = None
    error: Optional[Any] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OpenAIStreamStateMachine:
    """State machine that consumes streaming events into typed parsed data."""

    TEXT_DELTA_EVENT_TYPES = {"response.output_text.delta"}
    TEXT_DONE_EVENT_TYPES = {"response.output_text.done"}

    TOOL_DELTA_EVENT_TYPES = {
        "response.function_call.delta",
        "response.tool_call.delta",
        "response.function_call_arguments.delta",
    }
    TOOL_DONE_EVENT_TYPES = {
        "response.function_call.done",
        "response.tool_call.done",
        "response.function_call_arguments.done",
    }

    OUTPUT_ITEM_DONE_EVENT_TYPES = {"response.output_item.done"}
    COMPLETED_EVENT_TYPES = {"response.completed"}
    ERROR_EVENT_TYPES = {"response.error", "response.failed"}

    def __init__(
        self,
        on_text_delta: Optional[TextDeltaCallback] = None,
        on_tool_call: Optional[ToolCallCallback] = None,
    ) -> None:
        self.state_ = StreamConsumeState()
        self.on_text_delta_ = on_text_delta
        self.on_tool_call_ = on_tool_call

    # 最后返回的是一个最终的状态机
    def consume(self, stream: Iterable[Any]) -> StreamConsumeState:
        for event in stream:
            event_type = self._extract_event_type(event)
            if not event_type:
                continue

            if event_type in self.TEXT_DELTA_EVENT_TYPES:
                self._handle_text_delta(event)
                continue

            if event_type in self.TEXT_DONE_EVENT_TYPES:
                self._handle_text_done(event)
                continue

            if event_type in self.TOOL_DELTA_EVENT_TYPES:
                self._handle_tool_delta(event)
                continue

            if event_type in self.TOOL_DONE_EVENT_TYPES:
                self._handle_tool_done(event)
                continue

            if event_type in self.OUTPUT_ITEM_DONE_EVENT_TYPES:
                self._handle_output_item_done(event)
                continue

            if event_type in self.COMPLETED_EVENT_TYPES:
                self._handle_completed(event)
                continue

            if event_type in self.ERROR_EVENT_TYPES:
                self._handle_error(event)
                break

        self._flush_text_buffer()
        self._flush_pending_tool_buffers()
        return self.state_

    def _handle_text_delta(self, event: Any) -> None:
        delta = self._pick_string(event, ["delta"]) or self._pick_string(event, ["text"])
        if not delta:
            return

        self.state_.text_buffer += delta
        if self.on_text_delta_ is not None:
            try:
                self.on_text_delta_(delta)
            except Exception:
                # 回调属于扩展点，不应该影响主流程。
                pass

    def _handle_text_done(self, event: Any) -> None:
        final_text = self._pick_string(event, ["text"]) or self.state_.text_buffer
        if final_text:
            self._append_text_chunk(final_text)
        self.state_.text_buffer = ""

    def _handle_tool_delta(self, event: Any) -> None:
        call_id = self._pick_string(event, ["call_id", "id", "tool_call_id", "item_id"])
        if not call_id:
            source = self._pick_object(event, ["tool_call", "function_call", "item"])
            call_id = self._pick_string(source, ["call_id", "id"])

        if not call_id:
            return

        tool_name = self._pick_string(event, ["name", "tool_name"])
        if not tool_name:
            source = self._pick_object(event, ["tool_call", "function_call", "item"])
            tool_name = self._pick_string(source, ["name", "tool_name"])

        delta = self._pick_string(event, ["delta", "arguments_delta"])
        if not delta:
            source = self._pick_object(event, ["tool_call", "function_call", "item"])
            delta = self._pick_arguments_json(source)

        buf = self.state_.tool_buffers.get(call_id)
        if buf is None:
            buf = ToolCallBuffer(call_id=call_id)
            self.state_.tool_buffers[call_id] = buf

        if tool_name and not buf.tool_name:
            buf.tool_name = tool_name
        if delta:
            buf.arguments_json += delta

    def _handle_tool_done(self, event: Any) -> None:
        source = self._pick_object(event, ["tool_call", "function_call", "item"])

        call_id = self._pick_string(event, ["call_id", "id", "tool_call_id", "item_id"])
        if not call_id:
            call_id = self._pick_string(source, ["call_id", "id"])

        buf = self.state_.tool_buffers.get(call_id) if call_id else None

        parsed = self._build_parsed_tool_call(
            source=source,
            fallback_call_id=call_id,
            fallback_tool_name=buf.tool_name if buf is not None else "",
            fallback_arguments_json=buf.arguments_json if buf is not None else "",
        )
        if parsed is not None:
            self._record_tool_call(parsed)

        if call_id:
            self.state_.tool_buffers.pop(call_id, None)

    def _handle_output_item_done(self, event: Any) -> None:
        item = self._pick_object(event, ["item"])
        item_type = self._pick_string(item, ["type"])

        if item_type in {"function_call", "tool_call"}:
            self._handle_tool_done(event)
            return

        if item_type == "message":
            for text in self._extract_message_texts(item):
                self._append_text_chunk(text)

    def _handle_completed(self, event: Any) -> None:
        response_obj = self._pick_object(event, ["response"])
        if response_obj is not None:
            self.state_.completed_response = response_obj

    def _handle_error(self, event: Any) -> None:
        error_obj = self._pick_object(event, ["error"]) or self._pick_string(event, ["message", "error"])
        self.state_.error = error_obj

    def _flush_text_buffer(self) -> None:
        if self.state_.text_buffer:
            self._append_text_chunk(self.state_.text_buffer)
            self.state_.text_buffer = ""

    def _flush_pending_tool_buffers(self) -> None:
        for call_id, buf in list(self.state_.tool_buffers.items()):
            parsed = self._build_parsed_tool_call(
                source=None,
                fallback_call_id=call_id,
                fallback_tool_name=buf.tool_name,
                fallback_arguments_json=buf.arguments_json,
            )
            if parsed is not None:
                self._record_tool_call(parsed)
            self.state_.tool_buffers.pop(call_id, None)

    def _record_tool_call(self, tool_call: ParsedToolCall) -> None:
        if tool_call.call_id and tool_call.call_id in self.state_.seen_tool_call_ids:
            return

        if tool_call.call_id:
            self.state_.seen_tool_call_ids.add(tool_call.call_id)

        self.state_.tool_calls.append(tool_call)

        if self.on_tool_call_ is not None:
            try:
                self.on_tool_call_(tool_call)
            except Exception:
                # 回调属于扩展点，不应该影响主流程。
                pass

    def _build_parsed_tool_call(
        self,
        source: Any,
        fallback_call_id: Optional[str],
        fallback_tool_name: str,
        fallback_arguments_json: str,
    ) -> Optional[ParsedToolCall]:
        call_id = self._pick_string(source, ["call_id", "id"]) or (fallback_call_id or "")
        tool_name = self._pick_string(source, ["name", "tool_name"]) or fallback_tool_name
        arguments_json = self._pick_arguments_json(source) or fallback_arguments_json or "{}"

        if not call_id and not tool_name and not arguments_json:
            return None

        # Ignore malformed tool-call frames that do not provide a usable tool name.
        # In practice these frames are often transient duplicates from stream events.
        if not (tool_name or "").strip():
            return None

        return ParsedToolCall(
            tool_name=tool_name,
            call_id=call_id,
            arguments_json=arguments_json,
            arguments=self._parse_arguments(arguments_json),
        )

    def _append_text_chunk(self, text: str) -> None:
        if not text:
            return
        if self.state_.text_chunks and self.state_.text_chunks[-1].text == text:
            return
        self.state_.text_chunks.append(ParsedTextChunk(text=text))

    def _extract_message_texts(self, item: Any) -> List[str]:
        content_items = self._pick_list(item, ["content"])
        texts: List[str] = []
        for content in content_items:
            content_type = self._pick_string(content, ["type"])
            if content_type != "output_text":
                continue
            text = self._pick_string(content, ["text"])
            if text:
                texts.append(text)
        return texts

    def _extract_event_type(self, event: Any) -> str:
        return self._pick_string(event, ["type"])

    def _pick_string(self, source: Any, keys: List[str]) -> str:
        if source is None:
            return ""

        mapping = self._to_mapping(source)
        for key in keys:
            value = mapping.get(key)
            if value is None:
                value = getattr(source, key, None)
            if value is None:
                continue
            if isinstance(value, str):
                if value:
                    return value
                continue
            rendered = str(value)
            if rendered:
                return rendered
        return ""

    def _pick_arguments_json(self, source: Any) -> str:
        if source is None:
            return ""

        mapping = self._to_mapping(source)
        for key in ["arguments_json", "arguments", "args"]:
            value = mapping.get(key)
            if value is None:
                value = getattr(source, key, None)
            if value is None:
                continue
            if isinstance(value, str):
                return value
            try:
                return json.dumps(value, ensure_ascii=False)
            except TypeError:
                return str(value)
        return ""

    def _pick_object(self, source: Any, keys: List[str]) -> Optional[Any]:
        if source is None:
            return None

        mapping = self._to_mapping(source)
        for key in keys:
            value = mapping.get(key)
            if value is None:
                value = getattr(source, key, None)
            if value is not None:
                return value
        return None

    def _pick_list(self, source: Any, keys: List[str]) -> List[Any]:
        if source is None:
            return []

        mapping = self._to_mapping(source)
        for key in keys:
            value = mapping.get(key)
            if value is None:
                value = getattr(source, key, None)
            if value is None:
                continue
            if isinstance(value, list):
                return value
            try:
                return list(value)
            except TypeError:
                return []
        return []

    def _to_mapping(self, source: Any) -> Dict[str, Any]:
        if source is None:
            return {}

        model_dump = getattr(source, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if hasattr(dumped, "get"):
                return cast(Dict[str, Any], dumped)

        source_dict = getattr(source, "__dict__", None)
        if source_dict is not None and hasattr(source_dict, "get"):
            return source_dict

        if hasattr(source, "get") and hasattr(source, "keys"):
            return source

        return {}

    def _parse_arguments(self, arguments_json: str) -> Dict[str, Any]:
        if not arguments_json:
            return {}

        try:
            loaded = json.loads(arguments_json)
        except (TypeError, json.JSONDecodeError):
            return {}

        if isinstance(loaded, dict):
            return loaded
        return {}
