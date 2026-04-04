"""用于搭建简单的Agent壳，目前只需要保证能够循环思考调用即可，后续可逐步扩展功能"""
from abc import ABC, abstractmethod
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.message import Message
from typing import List, Optional
from frame.core.prompts import SYSTEM_PROMPT

class BaseAgent(ABC):
    def __init__(self, name:str,config: AgentConfig,llm: LLMClient):
        self.name_ = name
        self.config_ = config
        self.llm_ = llm
        self.history:List[Message] = []
        self.sys_prompt_ = None # 先不进行初始化

    # 构建Agent的初始状态，使用俩阶段初始化来避免构造函数的生命周期问题
    def build(self):
        prompt = self.init_sys_prompt()
        self.sys_prompt_ = prompt if prompt is not None else SYSTEM_PROMPT

    # 外部可以使用这个方法来观察是否已经完成了build，或者在think中调用以确保已经完成build
    def _ensure_built(self):
        if self.sys_prompt_ is None:
            raise RuntimeError("Agent must be built before use")

    # 轮次调用
    def think(self, input: str) -> str:
        self._ensure_built()
        return self._think_impl(input)
    
    @abstractmethod
    def _think_impl(self, input: str) -> str:
        pass
    
    # 子类可以重载该方法来提供特定的提示词，如果不重载则使用默认的系统提示词
    def init_sys_prompt(self)->str:
        return SYSTEM_PROMPT
