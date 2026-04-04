"""一个简单的计算器工具，支持加减乘除四则运算。

用法示例：
  - add 3 5
  - sub 10 4
  - mul 2 3
  - div 10 2

工具会把结果作为字符串返回，发生错误时返回错误描述。
"""
from typing import Any, Dict

from .base import Tool, ToolParameter

class Calculator(Tool):
    def __init__(self):
        super().__init__("Calculator", "一个简单的计算器工具，支持 add/sub/mul/div 三个参数：operation operand1 operand2")
        self.parameters = [
            ToolParameter(name="operation", type="str", description="add/sub/mul/div", required=True),
            ToolParameter(name="operand1", type="float", description="第一个数字", required=True),
            ToolParameter(name="operand2", type="float", description="第二个数字", required=True),
        ]

    def parse_input(self, input: str) -> Dict[str, Any]:
        parts = input.strip().split()
        if len(parts) != 3:
            raise ValueError("输入格式应为：operation operand1 operand2，例如：add 3 5")
        op = parts[0].lower()
        try:
            a = float(parts[1])
            b = float(parts[2])
        except ValueError:
            raise ValueError("operand 必须是数字")
        return {"operation": op, "operand1": a, "operand2": b}

    def run(self, input: str) -> str:
        params = self.parse_input(input)
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
                return "Error: division by zero"
            res = a / b
        else:
            return f"Unknown operation: {op}"
        # 优雅展示整数值
        if isinstance(res, float) and res.is_integer():
            return str(int(res))
        return str(res)

    @classmethod
    def description(cls) -> str:
        return "Calculator: 输入 'operation operand1 operand2'，operation 可为 add/sub/mul/div,operand1 和 operand2 为数字。"