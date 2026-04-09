"""工具注册与调用器（最简实现）。

提供注册、列举、描述和调用接口，便于 Agent 在运行时查询与调用工具。
"""
from typing import Dict, List, Optional
import time

from frame.tool.base import Tool
from frame.core.tool_protocol import normalize_tool_result
from frame.core.message import ToolMessage, ToolResult

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name_] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def describe(self, name: str) -> str:
        t = self.get(name)
        if not t:
            return ""
        try:
            return t.description()
        except Exception:
            return t.description_ if hasattr(t, "description_") else ""

    def invoke(self, name: str, tool_message: ToolMessage) -> ToolResult:
        """Invoke a registered tool using a ToolMessage object and return ToolResult.

        Strict mode: `tool_message` must be a ToolMessage object.
        The underlying `Tool.run` is expected to return a ToolResult object.
        """
        t = self.get(name)
        if not t:
            raise KeyError(f"Tool '{name}' not found")

        start = time.time()
        try:
            raw = t.run(tool_message)
        except Exception as e:
            tr = ToolResult(tool_name=name, status="error", error_message=str(e), original_input=tool_message)
            tr.duration_ms = int((time.time() - start) * 1000)
            return tr

        # Normalize tool result (raw is expected to be a ToolResult)
        tr = normalize_tool_result(raw, tool_name=name, original_input=tool_message.tool_input)
        if not tr.tool_name:
            tr.tool_name = name
        # ensure duration is filled
        if not tr.duration_ms:
            tr.duration_ms = int((time.time() - start) * 1000)

        # ensure there is a natural-language summary
        if not tr.nl:
            try:
                if tr.status == "ok":
                    tr.nl = str(tr.output)
                else:
                    tr.nl = tr.error_message or (str(tr.error_code) if tr.error_code is not None else "工具执行完成")
            except Exception:
                tr.nl = None

        return tr

    def invoke_json(self, name: str, tool_message: ToolMessage) -> str:
        """边界层序列化：返回 JSON 字符串，供旧调用方或日志使用。"""
        return self.invoke(name, tool_message).to_json(ensure_ascii=False)
    
    def describe_all(self) -> str:
        descriptions = []
        for name, tool in self._tools.items():
            desc = self.describe(name)
            descriptions.append(f"{name}: {desc}")
        return "\n".join(descriptions)
