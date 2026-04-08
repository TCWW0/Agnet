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
import json
import re

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
    def description() -> str:
        """
        返回供 LLM 注入的消息格式说明（用于系统提示）。

        要求模型严格按照说明输出：只返回合法的 JSON（单个对象或对象数组），
        不要包含额外的自然语言描述、注释或代码块。
        """
        return (
            "消息 JSON 格式说明（严格遵守，务必只输出 JSON）：\n"
            "\n"
            "聊天消息（type=\"chat\"）字段：\n"
            "  - type: \"chat\"\n"
            "  - role: 字符串，取值示例：\"user\", \"assistant\", \"system\"\n"
            "  - action: 字符串，示例：\"input\"、\"think\"、\"final\"、\"error\"\n"
            "  - content: 字符串，消息正文\n"
            "  - timestamp: 可选，ISO 8601 格式时间戳\n"
            "  - metadata: 可选，对象，携带任意额外元信息\n"
            "\n"
            "工具消息（type=\"tool\"）字段：\n"
            "  - type: \"tool\"\n"
            "  - tool_name: 字符串，工具名称\n"
            "  - tool_input: 字符串或对象，作为工具的输入\n"
            "  - phase: 字符串，取值：\"call\" | \"result\" | \"error\"\n"
            "  - raw: 可选，原始文本或调试信息\n"
            "  - timestamp/metadata: 可选，同聊天消息\n"
            "\n"
            "示例（单条聊天消息）：\n"
            "  {\"type\":\"chat\", \"role\":\"assistant\", \"action\":\"final\", \"content\":\"两数相加结果是 5。\"}\n"
            "示例（工具调用请求）：\n"
            "  {\"type\":\"tool\", \"tool_name\":\"Calculator\", \"tool_input\":\"add 2 3\", \"phase\":\"call\"}\n"
            "示例（多条消息）：\n"
            "  [ {" + "\"type\":\"chat\", \"role\":\"assistant\", \"action\":\"think\", \"content\":\"我需要计算\"}, {\"type\":\"tool\", \"tool_name\":\"Calculator\", \"tool_input\":\"add 2 3\", \"phase\":\"call\"} ]\n"
            "\n"
            "要求：严格只输出上述 JSON 对象或数组，禁止额外文本或说明；若无法回答，请返回一个 `chat` 类型的 `final` 消息并在 `content` 中说明无法回答的原因。"
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
    def spec() -> str:
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
            tool_example = "{\"type\":\"tool\",\"tool_name\":\"Calculator\",\"tool_input\":\"add 2 3\",\"phase\":\"call\"}"
            tool_desc = "工具消息请参见文档。"
        return (
            Message.description()
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
        pattern = re.compile(r'^(?P<action>think|tool_call|final|tool_result|tool_error)\s*[: ]?\s*(?P<content>.*)$', re.IGNORECASE)

        for ln in lines:
            m = pattern.match(ln)
            if m:
                action = m.group('action').lower()
                content = m.group('content')
                if action == 'think':
                    out.append(Message(role='assistant', action='think', content=content))
                    continue
                if action == 'final':
                    out.append(Message(role='assistant', action='final', content=content))
                    continue
                if action == 'tool_call':
                    # content is expected to be JSON containing name/input
                    try:
                        payload = json.loads(content)
                        name = payload.get('name') or payload.get('tool_name')
                        input_v = payload.get('input') or payload.get('tool_input')
                        out.append(ToolMessage(tool_name=name or '', tool_input=input_v or '', phase='call', raw=content))
                    except Exception:
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
            # fallback: treat line as final chat content
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
    def __init__(self, tool_name: str, tool_input: Union[str, Dict[str, Any], List[Any]], phase: str = "call", raw: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        # 不使用 super().__init__ 因为字段模型不同，但保留 type 字段
        self.type = "tool"
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.phase = phase
        self.raw = raw
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
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]):
        tool_name = obj.get("tool_name") or obj.get("name") or obj.get("tool")
        tool_input = obj.get("tool_input") if "tool_input" in obj else obj.get("input")
        phase = obj.get("phase", "call")
        raw = obj.get("raw")
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        ts = obj.get("timestamp")
        m = cls(tool_name=tool_name, tool_input=tool_input, phase=phase, raw=raw, metadata=metadata) # type: ignore
        if isinstance(ts, str):
            try:
                m.timestamp = datetime.fromisoformat(ts)
            except Exception:
                pass
        return m

    @staticmethod
    def description() -> str:
        return (
            "工具消息（type=\"tool\"）字段：\n"
            "  - type: \"tool\"\n"
            "  - tool_name: 字符串，工具名称\n"
            "  - tool_input: 字符串或对象，作为工具的输入\n"
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