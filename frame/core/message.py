"""
实现消息结构的标准化定义(使用OpenAI规范)，以便于消息的创建、解析和验证。
参考链接：https://developers.openai.com/api/reference/python/resources/responses/methods/create
"""
from __future__ import annotations

import datetime
import json
import time
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, Field

MessageType = Literal["text", "image", "file", "function", "tool_response"]


def _now_iso() -> str:
    return datetime.datetime.now().isoformat()


class Message(BaseModel):
    role: str
    content: str
    timestamp: float = Field(default_factory=time.time)
    time_str: str = Field(default_factory=_now_iso)
    type: MessageType = "text"

    model_config = ConfigDict(extra="forbid")

    def to_prompt(self) -> str:
        return f"{self.role}: {self.content}"


class UserTextMessage(Message):
    def __init__(self, content: str):
        super().__init__(role="user", content=content, type="text")


class LLMResponseTextMsg(Message):
    def __init__(self, content: str):
        super().__init__(role="assistant", content=content, type="text")


class LLMResponseFunCallMsg(Message):
    tool_name: str = ""
    call_id: str = ""
    arguments_json: str = "{}"
    arguments: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        tool_name: str,
        call_id: str,
        arguments_json: str,
        arguments: Dict[str, Any] | None = None,
    ) -> LLMResponseFunCallMsg:
        parsed_args: Dict[str, Any]
        if arguments is not None:
            parsed_args = arguments
        else:
            try:
                loaded = json.loads(arguments_json)
                parsed_args = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                parsed_args = {}

        return cls(
            role="assistant",
            content=arguments_json,
            type="function",
            tool_name=tool_name,
            call_id=call_id,
            arguments_json=arguments_json,
            arguments=parsed_args,
        )


class ToolResponseMessage(Message):
    tool_name: str
    call_id: str
    status: Literal["success", "error"]
    details: Dict[str, Any] | None = None

    @classmethod
    def from_tool_result(
        cls,
        tool_name: str,
        call_id: str,
        status: Literal["success", "error"],
        output: str,
        details: Dict[str, Any] | None = None,
    ) -> ToolResponseMessage:
        return cls(
            role="tool",
            content=output,
            type="tool_response",
            tool_name=tool_name,
            call_id=call_id,
            status=status,
            details=details,
        )


if __name__ == "__main__":
    msg = Message(role="user", content="Hello, how are you?")
    print(msg.to_prompt())