from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from frame.core.logger import Logger
from frame.tool.base import BaseTool, ToolDesc, ToolResponse

class ToolRegistry:
    def __init__(self, logger: Optional[Logger] = None):
        self.tools: List[BaseTool] = []
        self.logger_ = logger

    def register_tool(self, tool: BaseTool):
        self.tools.append(tool)

    def get_tools(self) -> List[BaseTool]:
        return self.tools
    
    def get_tool_by_name(self, name: str) -> BaseTool:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise ValueError(f"Tool with name '{name}' not found.")

    def set_logger(self, logger: Optional[Logger]) -> None:
        self.logger_ = logger

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResponse:
        try:
            tool = self.get_tool_by_name(name)
        except ValueError as exc:
            response = ToolResponse(tool_name=name, status="error", output=str(exc))
            self._log(
                "tool_result",
                name,
                {
                    "status": response.status,
                    "input": arguments,
                    "output": response.output,
                    "details": response.details,
                },
            )
            return response

        response = tool.execute(arguments)
        self._log(
            "tool_result",
            name,
            {
                "status": response.status,
                "input": arguments,
                "output": response.output,
                "details": response.details,
            },
        )
        return response
    
    def clear_tools(self):
        self.tools.clear()

    def get_tools_in_protocal(self) -> List[ToolDesc]:
        descs: List[ToolDesc] = []
        for tool in self.tools:
            descs.append(tool.desc())
        return descs

    def _log(self, event: str, tool_name: str, payload: Dict[str, Any]) -> None:
        if self.logger_ is None:
            return
        try:
            payload_text = json.dumps(payload, ensure_ascii=False)
        except Exception:
            payload_text = str(payload)
        self.logger_.info("ToolRegistry call %s name=%s payload=%s", event, tool_name, payload_text)
    
global_tool_registry = ToolRegistry()