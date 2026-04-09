from typing import Any, Dict, Union
import json

from .base import InputParser
from frame.core.message import Message, ToolMessage


class SimpleInputParser(InputParser):
    """简单的输入解析器：将 LLM 原始文本或 dict 解析为 ToolMessage 风格的 dict。

    行为：
    - 如果输入是 dict 且已经是 ToolMessage（type=="tool"），直接返回。
    - 如果输入是字符串，先尝试 JSON 解析为 dict 并返回（如果是 ToolMessage），否则使用
      Message.convert_many_from_str 从文本中提取第一个 ToolMessage。
    - 若未找到可用的 ToolMessage，会抛出 ValueError。
    """

    def parse_input(self, input: Union[str, Dict[str, Any]]) -> ToolMessage:
        if isinstance(input, dict):
            # 已是 ToolMessage 风格
            if input.get("type") == "tool":
                return ToolMessage.from_dict(input)
            # 兼容性：若存在 tool_input 字段，也视为 ToolMessage-like
            if "tool_input" in input:
                return ToolMessage(tool_name=input.get("tool_name", ""), tool_input=input.get("tool_input"), phase=input.get("phase", "call"), raw=input.get("raw"), metadata=input.get("metadata") if isinstance(input.get("metadata"), dict) else {}) # type: ignore
            raise ValueError("input dict is not ToolMessage-like")

        # 字符串路径
        s = str(input)
        # 尝试 JSON
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict) and parsed.get("type") == "tool":
                return ToolMessage.from_dict(parsed)
        except Exception:
            pass

        # 使用 Message.convert_many_from_str 提取 ToolMessage
        parsed_msgs = Message.convert_many_from_str(s)
        for m in parsed_msgs:
            if isinstance(m, ToolMessage):
                return m
        raise ValueError("no ToolMessage found in input")
