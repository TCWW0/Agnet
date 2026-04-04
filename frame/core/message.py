"""消息的定义，用于约定一条通用的沟通消息应该如何组织"""

from datetime import datetime
import re
import json

class Message:
    role: str               # 消息的角色，可以是"user", "assistant", "system"等
    action: str             # 消息的类型，对于用户来说，可以是input，对于Agent，可以是think、tool_call、final等，根据这个决定是否结束
    timestamp: datetime     # 消息的时间戳，记录消息的创建时间，方便后续有关时序的处理
    content: str            # 消息的内容，通常是一个文本字符串，后续可扩展为多媒体资源以及结构化数据等

    def __init__(self, role: str, action: str, content: str):
        self.role = role
        self.action = action
        self.content = content
        self.timestamp = datetime.now()

    # eg: [2024-06-01 12:00:00.123] system/init: ...
    def __str__(self) -> str:
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return f"[{ts}] {self.role} [{self.action}]: {self.content}"

    def to_log(self) -> str:
        """
        返回适合写入日志的一行文本（无内部时间戳），供日志记录使用。
        日志的时间戳由 logging 框架负责添加，避免在消息内部重复展示时间信息。
        """
        # 使用 role/action 的扁平格式，便于日志过滤和阅读，不包含内部时间戳
        return f"{self.role}/{self.action}: {self.content}"

    def to_prompt(self) -> str:
        """返回用于发送给 LLM 的消息行，不包含内部时间戳。"""
        return f"{self.role} [{self.action}]: {self.content}"
    
    # 用于向LLM描述如何生成一个格式化文本，用于注入到系统提示词中
    @staticmethod
    def description() -> str:
        # 要求格式化生成4个字段，同时按照空格进行分割，如果在每个字段内部出现空格，需要进行转义
        return f"请按照以下格式生成消息：action content，其中action字段只可取值为think、final，当你认为你已经可以回答当前问题时，使用final作为action字段，否则使用think作为action字段，字段之间用空格分隔，如果字段内部有空格，请使用/进行转义，如果内部存在/，请使用//进行转义。例如：final 你好/，/我是一个智能助手。"

    @classmethod
    def convert_from_str(cls, text: str):
        """把 LLM 输出的单行文本解析为 Message。

        解析规则：尽可能从文本开头识别出动作关键词 `think` 或 `final`（大小写不敏感），
        支持多种常见输出格式，例如：
          - "final 这是回答"
          - "[final]: 这是回答"
          - "assistant [final]: 这是回答"
        如果未能识别到动作关键词，则默认为 `final` 并把整段文本作为内容。

        内容中的转义规则：使用 `//` 表示原始的 `/`，使用单个 `/` 表示原始的空格。
        为了正确处理 `//`，解析顺序为先替换 `//` 为临时占位符，再把单斜杠替换为空格，最后把占位符替换回 `/`。
        """
        # 向后兼容：使用 convert_many_from_str 并返回第一条消息
        msgs = cls.convert_many_from_str(text)
        return msgs[0]

    @classmethod
    def convert_many_from_str(cls, text: str):
        """
        把 LLM 的输出解析为一系列按顺序的 Message。

        支持在同一段文本中出现多个动作（比如先 tool_call 再 think 再 final）的情形，
        将它们拆成独立的 Message 列表，按出现顺序返回。
        """
        s = text.strip()
        pattern = r"\b(think|tool_call|final)\b"
        matches = list(re.finditer(pattern, s, flags=re.IGNORECASE))
        if not matches:
            # 整段视为 final
            placeholder = "\0"
            content = s.replace("//", placeholder).replace("/", " ").replace(placeholder, "/").strip()
            content = " ".join(line.strip() for line in content.splitlines() if line.strip())
            return [cls(role="assistant", action="final", content=content)]

        msgs = []
        for idx, m in enumerate(matches):
            action = m.group(1).lower()
            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(s)
            segment = s[start:end]
            segment = re.sub(r'^[\s\]\)\:\-\,\[]+', '', segment).strip()

            if action == "tool_call":
                json_str = None
                start_idx = segment.find('{')
                if start_idx != -1:
                    depth = 0
                    for i in range(start_idx, len(segment)):
                        if segment[i] == '{':
                            depth += 1
                        elif segment[i] == '}':
                            depth -= 1
                            if depth == 0:
                                json_str = segment[start_idx:i + 1]
                                break
                if json_str is None:
                    try:
                        json.loads(segment)
                        json_str = segment
                    except Exception:
                        json_str = segment.splitlines()[0].strip()

                content = json_str
            else:
                placeholder = "\0"
                content = segment.replace("//", placeholder).replace("/", " ").replace(placeholder, "/").strip()
                content = " ".join(line.strip() for line in content.splitlines() if line.strip())

            msgs.append(cls(role="assistant", action=action, content=content))

        return msgs