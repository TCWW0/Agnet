from frame.core.base_agent import BaseAgent
from frame.core.base_llm import BaseLLM
from frame.core.config import AgentConfig, LLMConfig
from frame.core.logger import Logger, global_logger
from typing import Optional
from frame.core.message import Message,LLMResponseTextMsg,UserTextMessage

class SimpleAgent(BaseAgent):
    def __init__(self, config: AgentConfig, llm: BaseLLM, sys_prompt: Optional[str] = None, logger: Optional[Logger] = None):
        super().__init__(config, llm, sys_prompt, logger)

    def _think_impl(self, user_input: str):
        # 将用户输入添加到历史消息中
        self.history_.append(UserTextMessage(content=user_input))
        # 调用LLM进行思考，获取回复
        response_msg = self.llm_.invoke_streaming(self.history_)
        if response_msg:
            # 将LLM的回复添加到历史消息中
            print("Agent response length:", len(response_msg.content))
            self.history_.append(response_msg)
        else:
            print("Agent: (No response)")

if __name__ == "__main__":
    config = AgentConfig.from_env()
    llm = BaseLLM(LLMConfig.from_env())
    agent = SimpleAgent(config, llm)
    user_input = "请介绍一下你自己。"
    agent.think(user_input)