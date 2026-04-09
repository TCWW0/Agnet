"""用于搭建简单的Agent壳，目前只需要保证能够循环思考调用即可，后续可逐步扩展功能"""
import uuid

from abc import ABC, abstractmethod
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.message import Message, ToolMessage
from typing import List, Optional, Union
from datetime import datetime
from frame.core.prompts import SYSTEM_PROMPT
from frame.core.logger import Logger, global_logger

class BaseAgent(ABC):
    def __init__(self, 
                 name:str,
                 config: AgentConfig,
                 llm: LLMClient,
                 workflow_id: str = uuid.uuid4().hex,
                 logger: Logger = global_logger,
                 ):
        self.workflow_id_ = workflow_id
        self.name_ = name
        self.config_ = config
        self.llm_ = llm
        self.logger_ = logger
        # 历史以 `Message` / `ToolMessage` 对象列表为主，便于在代码中按类型处理
        self.history: List[Message] = []
        self.sys_prompt_ = None # 先不进行初始化

    def append_history(self, msg: Union[Message, ToolMessage]):
        """将一条消息追加到历史。

        语义化约束：历史层只接受已解析完成的 `Message` / `ToolMessage` 对象。
        边界层若拿到 dict 或 str，应先显式调用对应的 `from_dict` / `from_json`。
        """
        if not isinstance(msg, (Message, ToolMessage)):
            raise TypeError("append_history expects a Message or ToolMessage object")
        self.history.append(msg)

    def build_prompt(self) -> str:
        """把历史消息转为用于 LLM 的提示字符串（每条一行）。

        兼容旧的 Message 实例与字典表示。
        """
        lines: List[str] = []
        lines.append(self.sys_prompt_) # type: ignore
        for m in self.history:
            try:
                # Message/ToolMessage 都实现了 to_prompt
                lines.append(m.to_prompt())
            except Exception:
                lines.append(str(m))
        return "\n".join(lines)

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
    
    def history_to_str(self) -> str:
        """把历史消息转为字符串，便于日志记录或调试输出。"""
        lines: List[str] = []
        for m in self.history:
            try:
                lines.append(m.to_log())
            except Exception:
                lines.append(str(m))
        return "\n".join(lines) 
