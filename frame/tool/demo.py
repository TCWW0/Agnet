"""演示：列出并调用注册的工具。"""
from frame.tool import ToolRegistry
from frame.tool.calculator import Calculator

def main() -> None:
    registry = ToolRegistry()
    registry.register(Calculator())
    print("Available tools:", registry.list_tools())
    print("Calculator description:", registry.describe("Calculator"))
    example_msg = {"type": "tool", "tool_name": "Calculator", "tool_input": {"operation": "add", "operand1": 2, "operand2": 3}, "phase": "call"}
    result = registry.invoke("Calculator", example_msg)
    print("Example: add 2 3 ->", result.to_json(ensure_ascii=False))

if __name__ == "__main__":
    main()