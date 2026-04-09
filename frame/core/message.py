"""消息类型定义：
提供结构化的 `Message`（聊天消息）与 `ToolMessage`（工具调用消息），
并提供 JSON 序列化/反序列化的统一接口。

设计原则：
- `Message` 表示对话层面的消息（默认实现），保持与历史代码的构造签名兼容：
  `Message(role, action, content, ...)`。
- `ToolMessage` 专用于表示工具调用或工具返回，字段结构更明确，便于序列化。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, asdict, field
import json
import re


@dataclass
class ToolResult:
    """工具执行结果的标准结构。"""

    version: str = "1.0"
    type: str = "tool_result"
    tool_name: str = ""
    request_id: Optional[str] = None
    status: str = "ok"  # ok | error | partial
    output: Any = None
    original_input: Any = None
    nl: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, ensure_ascii: bool = False, **json_kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii, **json_kwargs)

    @classmethod
    def from_json(cls, data: str) -> "ToolResult":
        return cls.from_dict(json.loads(data))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolResult":
        d = dict(data)
        ts = d.get("timestamp")
        if not ts:
            ts = datetime.now().isoformat()
        else:
            ts = str(ts)
        return cls(
            version=d.get("version", "1.0"),
            type=d.get("type", "tool_result"),
            tool_name=d.get("tool_name", ""),
            request_id=d.get("request_id"),
            status=d.get("status", "ok"),
            output=d.get("output"),
            original_input=d.get("original_input"),
            nl=d.get("nl"),
            error_code=d.get("error_code"),
            error_message=d.get("error_message"),
            timestamp=ts,
            duration_ms=d.get("duration_ms"),
            meta=d.get("meta"),
        )

    @staticmethod
    def description(concise: bool = True) -> str:
        if concise:
            return (
                "ToolResult（type=\"tool_result\"）: "
                "{\"type\":\"tool_result\",\"tool_name\":\"TODO\",\"status\":\"ok|error\",\"output\":...,\"error_message\":...}"
            )
        return (
            "ToolResult（type=\"tool_result\"）字段：\n"
            "  - version: 协议版本，默认 \"1.0\"\n"
            "  - type: 固定 \"tool_result\"\n"
            "  - tool_name: 工具名称\n"
            "  - request_id: 可选，请求ID\n"
            "  - status: \"ok\" | \"error\" | \"partial\"\n"
            "  - output: 执行输出（任意 JSON 值）\n"
            "  - original_input: 原始输入\n"
            "  - nl: 可选，自然语言摘要\n"
            "  - error_code/error_message: 可选，错误码与错误描述\n"
            "  - timestamp: 时间戳（ISO 8601）\n"
            "  - duration_ms: 可选，耗时毫秒\n"
            "  - meta: 可选，附加信息\n"
        )

    @staticmethod
    def example() -> str:
        return json.dumps(
            {
                "type": "tool_result",
                "version": "1.0",
                "tool_name": "TODO",
                "status": "ok",
                "output": {"id": 1, "content": "买菜"},
                "nl": "ok id=1",
            },
            ensure_ascii=False,
        )

    def __str__(self) -> str:
        return (
            f"ToolResult(tool_name={self.tool_name}, status={self.status}, "
            f"output={self.output}, error_message={self.error_message})"
        )

class Message:
    """对话消息（ChatMessage 风格）。

    向后兼容：可通过 `Message(role, action, content)` 构造。
    序列化包含 `type` 字段（值为 'chat'），反序列化时会根据 `type` 分发到 `ToolMessage`。
    """
    def __init__(self, role: str, action: str, content: str,  metadata: Optional[Dict[str, Any]] = None):
        self.type = "chat"
        self.role = role
        self.action = action
        self.content = content
        self.timestamp = datetime.now()
        self.metadata = metadata or {}

    def __str__(self) -> str:
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return f"[{ts}] {self.role} [{self.action}]: {self.content}"

    def to_log(self) -> str:
        return f"{self.role}/{self.action}: {self.content}"

    def to_prompt(self) -> str:
        return f"{self.role} [{self.action}]: {self.content}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "role": self.role,
            "action": self.action,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_json(self, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii)

    @staticmethod
    def description(concise: bool = True) -> str:
        """
        返回供 LLM 注入的消息格式说明（用于系统提示）。

        要求模型严格按照说明输出：只返回合法的 JSON（单个对象或对象数组），
        不要包含额外的自然语言描述、注释或代码块。
        """
        if concise:
            return (
                "消息格式（精简版）：仅输出单行 action 或 JSON，不要额外解释。\n"
                "- action 仅限 think/tool_call/final。\n"
                "- tool_call 内容必须是单行 JSON: {\"name\":\"工具名\",\"input\":{...}}。\n"
                "- ChatMessage 示例: {\"type\":\"chat\",\"role\":\"assistant\",\"action\":\"final\",\"content\":\"...\"}\n"
                "- ToolMessage 示例: {\"type\":\"tool\",\"tool_name\":\"TODO\",\"tool_input\":{\"op\":\"list\"},\"phase\":\"call\"}\n"
                f"- {ToolResult.description(concise=True)}"
            )

        return (
            "消息 JSON 格式说明（仅输出 JSON）：\n"
            "\n"
            "ChatMessage（type=\"chat\"）字段：\n"
            "  - type, role, action, content, timestamp?, metadata?\n"
            "ToolMessage（type=\"tool\"）字段：\n"
            "  - type, tool_name, tool_input, phase(call|result|error), raw?, timestamp?, metadata?\n"
            f"{ToolResult.description(concise=False)}"
            "\n示例（ChatMessage）：\n"
            "  {\"type\":\"chat\",\"role\":\"assistant\",\"action\":\"final\",\"content\":\"完成\"}\n"
            "示例（ToolMessage）：\n"
            "  {\"type\":\"tool\",\"tool_name\":\"TODO\",\"tool_input\":{\"op\":\"add\",\"content\":\"买菜\"},\"phase\":\"call\"}\n"
            f"示例（ToolResult）：\n  {ToolResult.example()}"
        )

    @staticmethod
    def example() -> str:
        """返回一个聊天消息的 JSON 示例（字符串）。"""
        return json.dumps({
            "type": "chat",
            "role": "assistant",
            "action": "final",
            "content": "两数相加结果是 5。"
        }, ensure_ascii=False)

    @staticmethod
    def spec(concise: bool = True) -> str:
        """聚合各类消息说明与示例，并明确 action 的语义和使用规则，供系统提示注入。"""
        action_semantics = (
            "Action 语义（何时使用）：\n"
            "  - think: 内部思考或中间步骤，用于记录模型的短推理或意图，非最终用户可见；\n"
            "  - final: 最终用户可见的回答或错误说明，表示本轮已结束。\n"
            "  - error: 错误信息，用于记录和报告问题。\n"
            "\n"
            "使用规则：\n"
            "  1. 若需要调用外部工具，先（可选）输出 `think`，再输出 `tool` 类型的 `tool_call`，等待工具结果后再输出 `final`。\n"
            "  2. 每次响应最多包含一个 `final`；如果包含 `tool_call` 则不得同时包含 `final`。\n"
        )
        try:
            tool_example = ToolMessage.example()
            tool_desc = ToolMessage.description()
        except Exception:
            tool_example = "{\"type\":\"tool\",\"tool_name\":\"Calculator\",\"tool_input\":{\"operation\":\"add\",\"operand1\":2,\"operand2\":3},\"phase\":\"call\"}"
            tool_desc = "工具消息请参见文档。"
        return (
            Message.description(concise=concise)
            + "\n\n示例（聊天消息）：\n"
            + Message.example()
            + "\n\n"
            + tool_desc
            + "\n\n示例（工具消息）：\n"
            + tool_example
            + "\n\n"
            + action_semantics
        )

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]):
        t = obj.get("type", "chat")
        if t == "tool":
            return ToolMessage.from_dict(obj)
        role = obj.get("role", "assistant")
        action = obj.get("action", "final")
        content = obj.get("content", "")
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        ts = obj.get("timestamp")
        msg = cls(role=role, action=action, content=content, metadata=metadata)
        if isinstance(ts, str):
            try:
                msg.timestamp = datetime.fromisoformat(ts)
            except Exception:
                pass
        return msg

    @classmethod
    def from_json(cls, s: str):
        try:
            parsed = json.loads(s)
        except Exception:
            # 非 JSON：把原始文本作为聊天消息的 content 返回，便于平滑迁移,如果出现这个问题，需要回顾来修复
            return cls(role="assistant", action="final", content=str(s))

        if isinstance(parsed, list):
            out: List[Message] = []
            for p in parsed:
                if isinstance(p, dict):
                    out.append(cls.from_dict(p))
                else:
                    out.append(cls(role="assistant", action="final", content=str(p)))
            return out

        if isinstance(parsed, dict):
            return cls.from_dict(parsed)

        return cls(role="assistant", action="final", content=str(parsed))

    @staticmethod
    def convert_many_from_str(s: str) -> List[Union["Message", "ToolMessage"]]:
        """Parse an LLM raw string into a list of Message/ToolMessage objects.

        Supports:
        - JSON formatted single object or array (falls back to from_json)
        - action-line formats like:
            think some thought
            tool_call {"name":"Calculator","input":"add 2 3"}
            final the answer

        This makes the agent robust to LLMs that output human-friendly action lines.
        """
        # First, try JSON parse path using existing from_json
        try:
            parsed_json = json.loads(s)
            res = Message.from_json(s)
            if isinstance(res, list):
                return res
            return [res]
        except Exception:
            pass

        out: List[Union[Message, ToolMessage]] = []
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
        # Improved parsing: allow lines with optional leading timestamp or role
        action_re = re.compile(r"(?P<action>think|final|tool_call|tool_result|tool_error|tool/call|tool call)\s*[: ]?\s*(?P<content>.*)$", re.IGNORECASE)

        for ln in lines:
            # strip common prefixed timestamp or role annotations like "[2026-04-09 10:23:14.482] assistant "
            stripped = re.sub(r"^\s*\[[^\]]+\]\s*", "", ln)
            # also remove leading role markers like "assistant " or "user " if present
            stripped = re.sub(r"^\s*(assistant|user|system)\s*[:\-]\s*", "", stripped, flags=re.IGNORECASE)

            m = action_re.search(stripped)
            if m:
                action = m.group('action').lower().replace('/', '_').replace(' ', '_')
                content = m.group('content').strip()

                if action == 'think':
                    out.append(Message(role='assistant', action='think', content=content))
                    continue
                if action == 'final':
                    out.append(Message(role='assistant', action='final', content=content))
                    continue

                if action == 'tool_call':
                    # support two common formats:
                    # 1) tool_call: {"name":"TODO","input":{...}}
                    # 2) tool/call TODO: {...}  or TODO: {...}
                    parsed_payload = None
                    tool_name = ''
                    # try JSON first
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            parsed_payload = parsed
                            tool_name = parsed.get('name') or parsed.get('tool_name') or ''
                    except Exception:
                        parsed = None

                    if parsed_payload is None:
                        # try pattern like "TOOLNAME: {...}"
                        m2 = re.match(r"^(?P<tool>\w+)\s*:\s*(?P<body>\{.*)$", content)
                        if m2:
                            tool_name = m2.group('tool')
                            body = m2.group('body')
                            try:
                                parsed_payload = json.loads(body)
                            except Exception:
                                parsed_payload = None

                    if parsed_payload is not None:
                        # extract input
                        input_v = parsed_payload.get('input') if 'input' in parsed_payload else parsed_payload.get('tool_input') if 'tool_input' in parsed_payload else parsed_payload
                        out.append(ToolMessage(tool_name=tool_name or '', tool_input=input_v or '', phase='call', raw=content))
                    else:
                        out.append(ToolMessage(tool_name='', tool_input=content, phase='call', raw=content))
                    continue

                if action in ('tool_result', 'tool_error'):
                    try:
                        payload = json.loads(content)
                    except Exception:
                        payload = content
                    phase = 'result' if action == 'tool_result' else 'error'
                    if isinstance(payload, dict) and 'tool_name' in payload:
                        out.append(ToolMessage(tool_name=payload.get('tool_name', ''), tool_input=payload, phase=phase, raw=content))
                    else:
                        out.append(ToolMessage(tool_name='', tool_input=payload, phase=phase, raw=content))
                    continue

            # fallback: treat entire line as a normal assistant final message
            out.append(Message(role='assistant', action='final', content=ln))

        return out


class ToolMessage(Message):
    """工具调用相关的消息结构。

    字段说明：
    - `tool_name`: 工具名称
    - `tool_input`: 调用时的输入（字符串或对象）
    - `phase`: one of 'call'|'result'|'error'
    - `raw`: 可选的原始文本/调试信息
    示例格式：
    {
        "type": "tool",
        "tool_name": "Calculator",
        "tool_input": "add 2 3",
        "phase": "call"
    }
    """
    def __init__(self, tool_name: str, tool_input: Union[str, Dict[str, Any], List[Any]], phase: str = "call", raw: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None):
        if phase not in {"call", "result", "error"}:
            raise ValueError("ToolMessage.phase must be one of 'call', 'result', 'error'")
        # 不使用 super().__init__ 因为字段模型不同，但保留 type 字段
        self.type = "tool"
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.phase = phase
        self.raw = raw
        self.request_id = request_id
        self.timestamp = datetime.now()
        self.metadata = metadata or {}

    def __str__(self) -> str:
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return f"[{ts}] tool/{self.phase} {self.tool_name}: {self.tool_input}"

    def to_prompt(self) -> str:
        # 渲染为 LLM 可解析的单行 JSON 格式（向后兼容旧的 tool_call 解析约定）
        payload = {"name": self.tool_name, "input": self.tool_input}
        if self.phase == "call":
            return f"tool_call: {json.dumps(payload, ensure_ascii=False)}"
        if self.phase == "result":
            return f"tool_result: {json.dumps(self.tool_input, ensure_ascii=False) if isinstance(self.tool_input, (dict, list)) else str(self.tool_input)}"
        if self.phase == "error":
            return f"tool_error: {self.raw or str(self.tool_input)}"
        return f"tool_{self.phase}: {json.dumps(self.tool_input, ensure_ascii=False) if isinstance(self.tool_input, (dict, list)) else str(self.tool_input)}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "phase": self.phase,
            "raw": self.raw,
            "request_id": getattr(self, "request_id", None),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_json(self, ensure_ascii: bool = False) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=ensure_ascii)

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]):
        tool_name = obj.get("tool_name") or obj.get("name") or obj.get("tool")
        tool_input = obj.get("tool_input") if "tool_input" in obj else obj.get("input")
        phase = obj.get("phase", "call")
        raw = obj.get("raw")
        request_id = obj.get("request_id")
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        ts = obj.get("timestamp")
        m = cls(tool_name=tool_name, tool_input=tool_input, phase=phase, raw=raw, metadata=metadata, request_id=request_id) # type: ignore
        if isinstance(ts, str):
            try:
                m.timestamp = datetime.fromisoformat(ts)
            except Exception:
                pass
        return m

    @classmethod
    def from_json(cls, s: str):
        return cls.from_dict(json.loads(s))

    @staticmethod
    def description(concise: bool = False) -> str:
        if concise:
            return (
                "ToolMessage: {\"type\":\"tool\",\"tool_name\":\"TODO\",\"tool_input\":{...},\"phase\":\"call|result|error\"}"
            )
        return (
            "工具消息（type=\"tool\"）字段：\n"
            "  - type: \"tool\"\n"
            "  - tool_name: 字符串，工具名称\n"
            "  - tool_input: 结构化对象，作为工具的输入（建议为 dict）\n"
            "  - phase: 字符串，取值：\"call\" | \"result\" | \"error\"\n"
            "  - raw: 可选，原始文本或调试信息\n"
            "  - timestamp/metadata: 可选，同聊天消息\n"
        )

    @staticmethod
    def example() -> str:
        return json.dumps({
            "type": "tool",
            "tool_name": "Calculator",
            "tool_input": "add 2 3",
            "phase": "call"
        }, ensure_ascii=False)

# 兼容别名
ChatMessage = Message


# TODO: 设计工具返回Message格式