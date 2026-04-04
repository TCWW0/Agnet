"""工具注册与调用器（最简实现）。

提供注册、列举、描述和调用接口，便于 Agent 在运行时查询与调用工具。
"""
from typing import Dict, List, Optional

from .base import Tool

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

    def invoke(self, name: str, input_str: str) -> str:
        t = self.get(name)
        if not t:
            raise KeyError(f"Tool '{name}' not found")
        return t.run(input_str)
    
    def describe_all(self) -> str:
        descriptions = []
        for name, tool in self._tools.items():
            desc = self.describe(name)
            descriptions.append(f"{name}: {desc}")
        return "\n".join(descriptions)
