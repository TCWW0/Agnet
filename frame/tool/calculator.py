"""一个简单的计算器工具，支持加减乘除四则运算。

用法示例：
  - add 3 5
  - sub 10 4
  - mul 2 3
  - div 10 2

工具会把结果作为字符串返回，发生错误时返回错误描述。
"""
from typing import Any, Dict
import time

from .base import Tool, ToolParameter, InputParser, validate_tool_message
from frame.core.message import ToolMessage, ToolResult

class Calculator(Tool, InputParser):
    def __init__(self):
        super().__init__("Calculator", "一个简单的计算器工具，支持 add/sub/mul/div 三个参数：operation operand1 operand2")
        self.parameters = [
            ToolParameter(name="operation", type="str", description="add/sub/mul/div", required=True),
            ToolParameter(name="operand1", type="float", description="第一个数字", required=True),
            ToolParameter(name="operand2", type="float", description="第二个数字", required=True),
        ]

    def parse_input(self, input: str) -> ToolMessage:
        parts = input.strip().split()
        if len(parts) != 3:
            raise ValueError("输入格式应为：operation operand1 operand2，例如：add 3 5")
        op = parts[0].lower()
        try:
            a = float(parts[1])
            b = float(parts[2])
        except ValueError:
            raise ValueError("operand 必须是数字")
        return ToolMessage(
            tool_name=self.name_,
            tool_input={"operation": op, "operand1": a, "operand2": b},
            phase="call",
        )

    def run(self, tool_message: ToolMessage) -> ToolResult:
        start = time.time()
        try:
            # 严格要求 ToolMessage dict
            tm = validate_tool_message(tool_message)
        except Exception as e:
            tr = ToolResult(tool_name=self.name_, status="error", error_message=str(e), original_input=tool_message)
            tr.duration_ms = int((time.time() - start) * 1000)
            return tr

        tool_input = tm.tool_input
        # tool_input 必须为 dict（不接受字符串或 None）
        if not isinstance(tool_input, dict):
            tr = ToolResult(tool_name=self.name_, status="error", error_message="tool_input must be a dict; string inputs are not accepted", original_input=tm.tool_input)
            tr.duration_ms = int((time.time() - start) * 1000)
            return tr

        try:
            params = tool_input
            op = params["operation"]
            a = params["operand1"]
            b = params["operand2"]
            if op in ("add", "+", "plus", "sum"):
                res = a + b
            elif op in ("sub", "-", "minus"):
                res = a - b
            elif op in ("mul", "*", "times", "x"):
                res = a * b
            elif op in ("div", "/", "divide"):
                if b == 0:
                    tr = ToolResult(tool_name=self.name_, status="error", error_message="division by zero", original_input=tm.tool_input)
                    tr.duration_ms = int((time.time() - start) * 1000)
                    return tr
                res = a / b
            else:
                tr = ToolResult(tool_name=self.name_, status="error", error_message=f"Unknown operation: {op}", original_input=tm.tool_input)
                tr.duration_ms = int((time.time() - start) * 1000)
                return tr
            # 优雅展示整数值
            output = int(res) if isinstance(res, float) and res.is_integer() else res
            tr = ToolResult(tool_name=self.name_, status="ok", output=output, original_input=tm.tool_input, nl=f"计算结果是 {output}")
            tr.duration_ms = int((time.time() - start) * 1000)
            return tr
        except Exception as e:
            tr = ToolResult(tool_name=self.name_, status="error", error_message=str(e), original_input=tool_message, nl=f"工具执行失败：{str(e)}")
            tr.duration_ms = int((time.time() - start) * 1000)
            return tr

    @classmethod
    def description(cls) -> str:
        return "Calculator: 输入 'operation operand1 operand2'，operation 可为 add/sub/mul/div,operand1 和 operand2 为数字。"