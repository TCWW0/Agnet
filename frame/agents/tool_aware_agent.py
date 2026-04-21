"""
Tool-Aware Agent： 能够调用工具的Agent，使用OpenAI协议
"""
from typing import Optional

from frame.core.base_llm import BaseLLM
from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.logger import Logger, global_logger
from frame.memory.base import AgentMemoryHooks, InMemoryMemoryKernel, MemoryPolicy, MemoryToolFacade, build_memory_tools
from frame.tool.register import ToolRegistry, global_tool_registry
from frame.tool.builtin.calculater import CalculaterTool

class ToolAwareAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        llm: BaseLLM,
        tool_registry: Optional[ToolRegistry] = None,
        logger: Optional[Logger] = None,
        session_id: Optional[str] = None,
        memory_hooks: Optional[AgentMemoryHooks] = None,
        memory_tool_facade: Optional[MemoryToolFacade] = None,
        enable_memory_tools: bool = False,
        agent_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            config,
            llm,
            logger=logger or global_logger,
            session_id=session_id,
            memory_hooks=memory_hooks,
            agent_id=agent_id,
        )
        self.tool_registry_ = tool_registry or global_tool_registry
        self.tool_registry_.register_tool(CalculaterTool())

        if enable_memory_tools and memory_tool_facade is not None:
            for memory_tool in build_memory_tools(memory_tool_facade, self.session_ref_):
                self.tool_registry_.register_tool(memory_tool)

    def _think_impl(self, user_input: str):
        invoke_messages = self._prepare_invoke_messages(user_input)
        messages = self.llm_.invoke_streaming(
            invoke_messages,
            self.tool_registry_.get_tools(),
            self.sys_prompt_,
        )

        if not messages:
            print("Agent: (No response)")
            return

        self._commit_turn(user_input=user_input, llm_messages=messages)

if __name__ == "__main__":
    llm_config = LLMConfig.from_env()
    llm = BaseLLM(llm_config)
    agent_config = AgentConfig.from_env()
    memory_hock = AgentMemoryHooks(InMemoryMemoryKernel(), MemoryPolicy(enable_retrieval=True, retrieval_top_k=3))
    # 使用记忆，测试效果
    #agent = ToolAwareAgent(config=agent_config, llm=llm, memory_hooks=memory_hock, enable_memory_tools=False)
    # 不使用记忆，测试效果
    agent = ToolAwareAgent(config=agent_config, llm=llm, memory_hooks=None, enable_memory_tools=False)  
    while True:
        user_input = input("User: ")
        if user_input.lower() in {"exit", "quit"}:
            break
        agent.think(user_input)
        print()
    