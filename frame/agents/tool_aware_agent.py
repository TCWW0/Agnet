"""
Tool-Aware Agent： 能够调用工具的Agent，使用OpenAI协议
"""
from typing import Optional

from frame.core.base_llm import BaseLLM
from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.logger import Logger, global_logger
from frame.core.message import LLMResponseTextMsg, UserTextMessage
from frame.tool.register import ToolRegistry, global_tool_registry
from frame.tool.builtin.calculater import CalculaterTool

class ToolAwareAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM,
        tool_registry: Optional[ToolRegistry] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        super().__init__(config, llm, logger=logger or global_logger)
        self.tool_registry_ = tool_registry or global_tool_registry
        self.tool_registry_.register_tool(CalculaterTool())

    def _think_impl(self, user_input: str):
        self.history_.append(UserTextMessage(content=user_input))
        messages = self.llm_.invoke(self.history_, self.tool_registry_.get_tools())

        if not messages:
            print("Agent: (No response)")
            return

        self.history_.extend(messages)
        for msg in messages:
            if isinstance(msg, LLMResponseTextMsg):
                print(msg.content)

if __name__ == "__main__":
    llm_config = LLMConfig.from_env()
    llm = BaseLLM(llm_config)
    agent_config = AgentConfig.from_env()
    agent = ToolAwareAgent(config=agent_config, llm=llm)
    while True:
        user_input = input("User: ")
        if user_input.lower() in {"exit", "quit"}:
            break
        agent.think(user_input)
    