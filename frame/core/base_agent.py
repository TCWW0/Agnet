"""
Base Agent
定义一个Agent所应该具备的基础属性以及方法
"""
import uuid
from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig
from frame.core.logger import Logger, global_logger
from frame.core.message import Message, UserTextMessage
from frame.core.prompts import SYS_PROMPT
from frame.memory.base import AgentMemoryHooks, SessionRef


class BaseAgent(ABC):
    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM,
        sys_prompt: Optional[str] = None,
        logger: Optional[Logger] = None,
        session_id: Optional[str] = None,
        memory_hooks: Optional[AgentMemoryHooks] = None,
        agent_id: Optional[str] = None,
    ):
        self.config_ = config
        self.llm_ = llm
        self.history_: List[Message] = []
        self.sys_prompt_: str = sys_prompt if sys_prompt is not None else SYS_PROMPT
        self.history_.append(Message(role="system", content=self.sys_prompt_))
        self.logger_ = logger if logger is not None else global_logger
        self.cur_cost_tokens_: int = 0      # 可用于本地的简单统计

        self.session_id_ = session_id or str(uuid.uuid4())
        self.session_ref_ = SessionRef(session_id=self.session_id_, agent_id=agent_id or self.__class__.__name__)
        self.memory_hooks_ = memory_hooks

    # 子Agent必须通过重写该方法来实现自己需要的思考逻辑
    @abstractmethod
    def _think_impl(self, user_input: str):
        pass

    def think(self, user_input: str):
        # TODO: 可以在这里添加一些通用的前置处理逻辑，比如输入的预处理，或者历史消息的管理等
        self._think_impl(user_input)

    def _prepare_invoke_messages(self, user_input: str) -> List[Message]:
        """Build request messages with optional forced memory injection."""
        user_msg = UserTextMessage(content=user_input)
        base_messages = [*self.history_, user_msg]

        if self.memory_hooks_ is None:
            return base_messages

        return self.memory_hooks_.before_invoke(
            session=self.session_ref_,
            user_input=user_input,
            base_messages=base_messages,
        )

    def _commit_turn(self, user_input: str, llm_messages: Sequence[Message], include_user: bool = True) -> None:
        """Persist one round into local history and optional memory kernel."""
        appended_messages: List[Message] = []

        if include_user:
            user_msg = UserTextMessage(content=user_input)
            self.history_.append(user_msg)
            appended_messages.append(user_msg)

        for msg in llm_messages:
            self.history_.append(msg)
            appended_messages.append(msg)

        if self.memory_hooks_ is not None:
            self.memory_hooks_.after_invoke(self.session_ref_, appended_messages)
