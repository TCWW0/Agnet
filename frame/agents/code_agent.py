"""
Code Agent
"""

from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig
from frame.core.logger import Logger
from frame.memory.base import AgentMemoryHooks

class CodeAgent(BaseAgent):
    def __init__(self, config: AgentConfig, llm: BaseLLM, sys_prompt: str | None = None, logger: Logger | None = None, session_id: str | None = None, memory_hooks: AgentMemoryHooks | None = None, agent_id: str | None = None):
        super().__init__(config, llm, sys_prompt, logger, session_id, memory_hooks, agent_id)