"""演示：列出并调用注册的工具。"""
from frame.tool import ToolRegistry
from frame.tool.calculator import Calculator

def main() -> None:
    registry = ToolRegistry()
    registry.register(Calculator())
    print("Available tools:", registry.list_tools())
    print("Calculator description:", registry.describe("Calculator"))
    print("Example: add 2 3 ->", registry.invoke("Calculator", "add 2 3"))

if __name__ == "__main__":
    main()