"""
Base Agent
定义一个Agent所应该具备的基础属性以及方法
"""
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig
from frame.core.message import Message,LLMResponseTextMsg,UserTextMessage
from frame.core.prompts import SYS_PROMPT
from frame.core.logger import Logger, global_logger

from typing import List, Optional
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    def __init__(self, config: AgentConfig, llm: BaseLLM,sys_prompt: Optional[str] = None, logger: Optional[Logger] = None):
        self.config_ = config
        self.llm_ = llm
        self.history_: List[Message] = []
        self.sys_prompt_: str = sys_prompt if sys_prompt is not None else SYS_PROMPT
        self.history_.append(Message(role="system", content=self.sys_prompt_))
        self.logger_ = logger if logger is not None else global_logger
        self.cur_cost_tokens_: int = 0      # 可用于本地的简单统计

    # 子Agent必须通过重写该方法来实现自己需要的思考逻辑
    @abstractmethod
    def _think_impl(self, user_input: str):
        pass

    def think(self, user_input: str):
        # TODO: 可以在这里添加一些通用的前置处理逻辑，比如输入的预处理，或者历史消息的管理等
        self._think_impl(user_input)
