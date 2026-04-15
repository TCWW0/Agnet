from frame.tool.base import BaseTool,ToolDesc,ToolParameters,Property,ToolResponse

from typing import Dict

class CalculaterTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="calculater",
            description="一个简单的计算工具，能够计算加减乘除四则运算",
        )

    @classmethod
    def desc(cls) -> ToolDesc:
        parm1 = Property(
            type="string",
            description="第一个操作数，支持整数和小数"
        )
        parm2 = Property(
            type="string",
            description="第二个操作数，支持整数和小数"
        )
        operator = Property(
            type="string",
            description="运算符，支持加减乘除：+ - * /",
            enum=["+", "-", "*", "/"]
        )

        params = ToolParameters(
            properties={
                "operand1": parm1,
                "operand2": parm2,
                "operator": operator,
            },
            required=["operand1", "operand2", "operator"]
        )

        return ToolDesc(
            name="calculater",
            description="对两个操作数执行四则运算，参数为两个操作数和一个运算符（+ - * /）",
            parameters=params,
        )
    
    # 只要重载这个方法，后续执行时就会在实际执行之前先调用valid_paras进行参数验证，确保参数的合法性
    def valid_paras(self, params: Dict[str, str]) -> bool:
        try:
            float(params["operand1"])
            float(params["operand2"])
            if params["operator"] not in ["+", "-", "*", "/"]:
                return False
            return True
        except:
            return False

    # 由OOP保证了执行此方法时传入的参数已经过valid_paras的验证，因此可以直接进行计算逻辑的实现
    def _execute_impl(self, params: Dict[str,str]) -> ToolResponse:
        operand1 = float(params["operand1"])
        operand2 = float(params["operand2"])
        operator = params["operator"]

        if operator == "+":
            result = operand1 + operand2
        elif operator == "-":
            result = operand1 - operand2
        elif operator == "*":
            result = operand1 * operand2
        else:
            result = operand1 / operand2

        # 一般来说，推荐工具输出是语义化的结果，而不是直接的原始结果，这样更利于LLM后续的理解和处理
        output = f"{operand1} {operator} {operand2} 的结果为 {result}"
        return ToolResponse(tool_name=self.name, status="success", output=output)