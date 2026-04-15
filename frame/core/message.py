"""
实现消息结构的标准化定义(使用OpenAPI规范)，以便于消息的创建、解析和验证。
参考链接：https://developers.openai.com/api/reference/python/resources/responses/methods/create
"""
import datetime
import json
import time
from pydantic import BaseModel
from typing import Literal,Dict

MessageType = Literal["text", "image", "file", "function", "tool_response"]

class Message(BaseModel):
    role: str
    content: str
    timestamp: float = time.time()  # 用于计算
    time_str: str                   # 用于展示
    type: MessageType = "text"

    def __init__(self, role: str, content: str, type: MessageType = "text"):
        super().__init__(
            role=role,
            content=content,
            timestamp=time.time(),
            time_str=datetime.datetime.now().isoformat(),
            type=type
        )

    def to_prompt(self) -> str:
        return f"{self.role}: {self.content}"

class UserTextMessage(Message):
    def __init__(self, content: str):
        super().__init__(role="user", content=content, type="text")

# LLM返回的文本结构消息
class LLMResponseTextMsg(Message):
    def __init__(self, content: str):
        super().__init__(role="assistant", content=content, type="text")

# 额外需要一个arguments字段来存储函数调用的参数,此时不需要content字段了
class LLMResponseFunCallMsg(Message):
    arguments: Dict[str,str] = {}
    def __init__(self, arguments: str):
        super().__init__(role="assistant", content="", type="function")
        # arguments为一个json格式的字符串，需要解析成字典
        try:
            self.arguments = json.loads(arguments)
        except json.JSONDecodeError:
            self.arguments = {}
    
if __name__ == "__main__":
    msg = Message(role="user", content="Hello, how are you?")
    print(msg.to_prompt())