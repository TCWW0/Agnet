"""使用ReAct范式的Agent实现，支持工具调用和流式输出"""
from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.logger import Logger, global_logger
from frame.core.message import LLMResponseTextMsg, UserTextMessage
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
    ) -> None:
        super().__init__(config, llm, logger=logger or global_logger)
        self.tool_registry_ = tool_registry or global_tool_registry
        self.tool_registry_.register_tool(CalculaterTool())

    def _think_impl(self, user_input: str):
        self.history_.append(UserTextMessage(content=user_input))
        # 使用流式接口展示模型令牌，同时让 orchestrator 负责工具调用（AUTO 模式）和多轮循环
        def _token_printer(token: str) -> None:
            # 简单地按字符打印到 stdout，保持流式显示
            print(token, end="", flush=True)

        tools = self.tool_registry_.get_tools()
        messages = self.llm_.invoke_streaming(
            self.history_, tools, self.sys_prompt_, on_token_callback=_token_printer
        )

        # 换行以结束流式输出
        print()

        if not messages:
            print("Agent: (No response)")
            return

        # 将返回的消息逐条处理并加入历史。Orchestrator 在 AUTO 模式下会自动执行工具并把结果作为 ToolResponseMessage 返回。
        final_text: Optional[LLMResponseTextMsg] = None
        for msg in messages:
            # 文本消息
            if getattr(msg, "type", "") == "text":
                #print(f"Assistant: {msg.content}")
                self.history_.append(msg)
                # 记录最后一条文本作为最终回答
                final_text = msg  # type: ignore[assignment]
                continue

            # 函数/工具调用（通常已由 Orchestrator 执行或在消息流中展示）
            if getattr(msg, "type", "") == "function":
                tool_name = getattr(msg, "tool_name", "")
                args = getattr(msg, "arguments", {})
                print(f"Assistant requested tool '{tool_name}' with args={args}")
                self.history_.append(msg)
                continue

            # 工具执行结果
            if getattr(msg, "type", "") == "tool_response":
                tool_name = getattr(msg, "tool_name", "")
                print(f"Tool '{tool_name}' -> {msg.content}")
                self.history_.append(msg)
                continue

            # 其他类型直接加入历史以保持对话上下文
            self.history_.append(msg)


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