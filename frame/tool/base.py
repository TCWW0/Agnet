"""所有工具的基类"""
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any, Dict

from frame.core.message import ToolMessage, ToolResult

"""一个参数的定义，包含名称、类型、描述、是否必需以及默认值等信息"""
class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
from typing import Any, Dict


class InputParser(ABC):
    """可选的输入解析器接口（mix-in）。

    实现该接口的工具可以被上层调用以将 LLM 原始文本解析为结构化的 ToolMessage/参数。
    该接口是可选的，`Tool` 基类不再强制要求实现解析方法。
    """
    @abstractmethod
    def parse_input(self, input: str) -> Any:
        """将原始输入解析为结构化对象（通常为 ToolMessage 对象或类似格式）。

        注意：`InputParser` 是可选的 mixin，用于将 LLM 原始文本解析为
        结构化 `tool_input` 字段。工具的 `run()` 方法不再接受原始字符串，
        而应接受一个已构造好的 `ToolMessage` 对象。
        """
        raise NotImplementedError()


class Tool(ABC):
    def __init__(self, name: str, description: str):
        self.name_ = name
        self.description_ = description

    @abstractmethod
    def run(self, tool_message: ToolMessage) -> ToolResult:
        """执行工具的核心方法。

        严格约定：只接受 `ToolMessage` 对象，不再接受原始字符串或裸字典输入。
        返回值为结构化的 `ToolResult` 对象（不要返回 JSON 字符串）。
        """
        raise NotImplementedError("子类必须实现 run 方法")

    @classmethod
    @abstractmethod
    def description(cls) -> str:
        """返回工具的描述信息，包括工具本身的描述以及对应的参数的描述"""
        raise NotImplementedError("子类必须实现 description 方法")


def validate_tool_message(obj: Any) -> ToolMessage:
    """验证并返回 `ToolMessage` 对象。

    - 必须为 `ToolMessage` 实例。
    - 工具侧应尽量将 `tool_input` 保持为对象或结构化值。

    在严格模式下，若传入字符串或其他类型将抛出 TypeError/ValueError。
    """
    if not isinstance(obj, ToolMessage):
        raise TypeError("Tool.run expects a ToolMessage object; bare dict/string inputs are not accepted")
    return obj