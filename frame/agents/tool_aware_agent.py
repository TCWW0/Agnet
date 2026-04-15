"""
Tool-Aware Agent： 能够调用工具的Agent，使用OpenAI协议
"""
from frame.core.base_llm import BaseLLM
from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig
from frame.tool.register import ToolRegistry

class ToolAwareAgent(BaseAgent):
    def __init__(self,config:AgentConfig,llm: BaseLLM) -> None:
        super().__init__(config, llm)

    def _think_impl(self, user_input: str):
        return super()._think_impl(user_input)
    