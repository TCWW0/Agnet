from base import BaseTool,ToolDesc
from typing import List

class ToolRegistry:
    def __init__(self):
        self.tools: List[BaseTool] = []

    def register_tool(self, tool: BaseTool):
        self.tools.append(tool)

    def get_tools(self) -> List[BaseTool]:
        return self.tools
    
    def get_tool_by_name(self, name: str) -> BaseTool:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise ValueError(f"Tool with name '{name}' not found.")
    
    def clear_tools(self):
        self.tools.clear()

    def get_tools_in_protocal(self) -> List[ToolDesc]:
        descs: List[ToolDesc] = []
        for tool in self.tools:
            descs.append(tool.desc())
        return descs
    
global_tool_registry = ToolRegistry()