"""使用ReAct范式的Agent实现，支持工具调用和流式输出"""
from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.logger import Logger, global_logger
from frame.memory.base import AgentMemoryHooks, MemoryToolFacade, build_memory_tools
from frame.tool.register import ToolRegistry, global_tool_registry
from frame.tool.builtin.calculater import CalculaterTool

from typing import Optional

class ReactAgent(BaseAgent):
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

        # 使用流式接口展示模型令牌，同时让 orchestrator 负责工具调用（AUTO 模式）和多轮循环
        def _token_printer(token: str) -> None:
            # 简单地按字符打印到 stdout，保持流式显示
            print(token, end="", flush=True)

        tools = self.tool_registry_.get_tools()
        messages = self.llm_.invoke_streaming(
            invoke_messages,
            tools,
            self.sys_prompt_,
            on_token_callback=_token_printer,
        )

        # 换行以结束流式输出
        print()

        if not messages:
            print("Agent: (No response)")
            return

        # 将返回的消息逐条处理并展示。Orchestrator 在 AUTO 模式下会自动执行工具并返回 ToolResponseMessage。
        for msg in messages:
            # 函数/工具调用（通常已由 Orchestrator 执行或在消息流中展示）
            if getattr(msg, "type", "") == "function":
                tool_name = getattr(msg, "tool_name", "")
                args = getattr(msg, "arguments", {})
                print(f"Assistant requested tool '{tool_name}' with args={args}")
                continue

            # 工具执行结果
            if getattr(msg, "type", "") == "tool_response":
                tool_name = getattr(msg, "tool_name", "")
                print(f"Tool '{tool_name}' -> {msg.content}")

        self._commit_turn(user_input=user_input, llm_messages=messages)


if __name__ == "__main__":
    # 简易交互示例
    llm_config = LLMConfig.from_env()
    llm = BaseLLM(llm_config)
    agent_config = AgentConfig.from_env()
    agent = ReactAgent(config=agent_config, llm=llm)
    print("ReAct Agent 启动。输入 'exit' 或 'quit' 退出。")
    while True:
        user_input = input("User: ")
        if user_input.lower() in {"exit", "quit"}:
            break
        agent.think(user_input)
        print()