"""所有工具的基类"""
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any

"""一个参数的定义，包含名称、类型、描述、是否必需以及默认值等信息"""
class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None

class Tool(ABC):
    def __init__(self, name:str, description:str):
        self.name_ = name
        self.description_ = description

    @abstractmethod
    def run(self, input:str) -> str:
        """执行工具的核心方法，接受一个字符串输入，返回一个字符串输出"""
        raise NotImplementedError("子类必须实现 run 方法")
    
    @abstractmethod
    def parse_input(self, input:str):
        """解析输入字符串为所需要的参数"""
        raise NotImplementedError("子类必须实现 parse_input 方法")

    @classmethod
    @abstractmethod
    def description(cls) -> str:
        """返回工具的描述信息，包括工具本身的描述以及对应的参数的描述"""
        raise NotImplementedError("子类必须实现 description 方法")