from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from frame.core.message import Message
from frame.tool.base import BaseTool, ToolResponse


class ToolCallMode(str, Enum):
    """Control how tool calls are handled after parsing model output."""

    OFF = "off"
    MANUAL = "manual"
    AUTO = "auto"


class RetryPolicy(BaseModel):
    """Retry settings for model API calls."""

    max_attempts: int = Field(default=1, ge=1)
    backoff_seconds: float = Field(default=0.0, ge=0.0)


TextDeltaCallback = Callable[[str], None]

# 一次执行的策略，包含工具调用模式、最大工具调用轮数、重试策略等
class InvocationPolicy(BaseModel):
    """Execution policy for one LLM invocation."""

    tool_mode: ToolCallMode = ToolCallMode.OFF
    max_tool_rounds: int = Field(default=3, ge=0)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_seconds: Optional[float] = Field(default=None, gt=0.0)
    failure_strategy_stub: str = "todo"

# 将用户所提供的参数统一包装成一个对象，方便后续扩展和维护
class InvocationRequest(BaseModel):
    """Typed request object passed into the middleware layer."""

    messages: List[Message]
    tools: List[BaseTool] = Field(default_factory=list)
    instructions: Optional[str] = None  # 按照OpenAI所说，该字段可以指定本次会话使用的系统提示词
    stream: bool = False
    policy: InvocationPolicy = Field(default_factory=InvocationPolicy)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ParsedTextChunk(BaseModel):
    text: str


class ParsedToolCall(BaseModel):
    tool_name: str
    call_id: str
    arguments_json: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ParsedResponse(BaseModel):
    response_id: Optional[str] = None
    texts: List[ParsedTextChunk] = Field(default_factory=list)
    tool_calls: List[ParsedToolCall] = Field(default_factory=list)


class ToolExecutionRecord(BaseModel):
    call: ParsedToolCall
    result: ToolResponse


class OpenAIInputItem(BaseModel):
    """A typed wrapper for payload item sent to Responses API input."""

    payload: Dict[str, Any]


class OpenAIToolSpec(BaseModel):
    """A typed wrapper for one tool spec payload sent to Responses API."""

    payload: Dict[str, Any]


class InvocationResult(BaseModel):
    """Structured result for one orchestrated invocation."""

    emitted_messages: List[Message] = Field(default_factory=list)
    response_ids: List[str] = Field(default_factory=list)
    tool_execution_records: List[ToolExecutionRecord] = Field(default_factory=list)
    total_tool_rounds: int = 0
    stopped_reason: str = "completed"

    model_config = ConfigDict(arbitrary_types_allowed=True)
