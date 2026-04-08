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
        # 迁移策略：append_history 接受 Message | ToolMessage | dict | str
        self.history: List[Message] = []
        self.sys_prompt_ = None # 先不进行初始化

    def append_history(self, msg: Union[Message, ToolMessage, dict, str]):
        """将一条消息追加到历史，内部以 `Message`/`ToolMessage` 对象存储。

        支持输入类型：
        - `Message` / `ToolMessage`：直接追加
        - `dict`：通过 `Message.from_dict`/`ToolMessage.from_dict` 解析
        - `str`：优先尝试 JSON 解析（支持数组/对象），否则封装为 `Message`（聊天消息）
        """
        # 已经是对象，直接追加
        if isinstance(msg, (Message, ToolMessage)):
            self.history.append(msg)
            return

        # dict -> 反序列化为相应消息对象
        if isinstance(msg, dict):
            try:
                m = Message.from_dict(msg)
                self.history.append(m)
            except Exception:
                # 最后兜底：把 dict 作为聊天消息的 content 字段
                m = Message(role="assistant", action="final", content=str(msg))
                self.history.append(m)
            return

        # str -> 先尝试 JSON 解析为 Message(s)
        if isinstance(msg, str):
            try:
                parsed = Message.from_json(msg)
                if isinstance(parsed, list):
                    for p in parsed:
                        if isinstance(p, (Message, ToolMessage)):
                            self.history.append(p)
                        elif isinstance(p, dict):
                            try:
                                self.history.append(Message.from_dict(p))
                            except Exception:
                                self.history.append(Message(role="assistant", action="final", content=str(p)))
                    return
                if isinstance(parsed, (Message, ToolMessage)):
                    self.history.append(parsed)
                    return
            except Exception:
                pass

            # 非 JSON 文本 -> 按聊天消息存储（向后兼容）
            self.history.append(Message(role="assistant", action="final", content=msg))
            return

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
