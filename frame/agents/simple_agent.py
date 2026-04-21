from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.logger import Logger, global_logger
from frame.memory.base import AgentMemoryHooks
from typing import Optional
from frame.core.message import UserTextMessage, Message

class SimpleAgent(BaseAgent):
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
        super().__init__(
            config,
            llm,
            sys_prompt,
            logger,
            session_id=session_id,
            memory_hooks=memory_hooks,
            agent_id=agent_id,
        )

    def _think_impl(self, user_input: str):
        invoke_messages = self._prepare_invoke_messages(user_input)
        response_messages = self.llm_.invoke_streaming(invoke_messages)
        if not response_messages:
            print("Agent: (No response)")
            return

        self._commit_turn(user_input=user_input, llm_messages=response_messages)

class SimpleAgentWithoutMemory(SimpleAgent):
    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM,
        sys_prompt: Optional[str] = None,
        logger: Optional[Logger] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        super().__init__(
            config,
            llm,
            sys_prompt,
            logger,
            session_id=session_id,
            memory_hooks=None,  # 不使用记忆钩子
            agent_id=agent_id,
        )

    def _think_impl(self, user_input: str):
        # 直接构建消息列表，不使用记忆钩子
        self.history_.append(UserTextMessage(content=user_input))
        response_messages = self.llm_.invoke_streaming(self.history_)
        if not response_messages:
            print("Agent: (No response)")
            return
        self.history_.extend(response_messages)  # 将模型回复也加入历史

if __name__ == "__main__":
    config = AgentConfig.from_env()
    llm = BaseLLM(LLMConfig.from_env())
    agent = SimpleAgent(config, llm)
    user_input = "请介绍一下你自己。"
    agent.think(user_input)