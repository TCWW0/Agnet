"""tool 包初始化：导出工具注册类与常用工具类，避免自动注册全局实例。

外部代码应显式创建 `ToolRegistry()` 实例并按需注册工具，从而能为不同 Agent 配置不同工具集。
"""
from .registry import ToolRegistry
from .calculator import Calculator

__all__ = ["ToolRegistry", "Calculator"]
