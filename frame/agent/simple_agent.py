"""最基础的Agent实现，只需要通过think调用底层的LLM接口输出即可"""
import logging
from typing import List

from frame.core.base_agent import BaseAgent
from frame.core.config import LLMConfig, AgentConfig
from frame.core.llm import LLMClient
from frame.core.prompts import SYSTEM_PROMPT
from frame.core.message import Message
from frame.core.logging_config import setup_logging

class SimpleAgent(BaseAgent):
    def __init__(self, name: str, config: AgentConfig, llm: LLMClient):
        # Ensure logging is configured once
        setup_logging()
        super().__init__(name, config, llm)
        self.logger = logging.getLogger(f"agent.{self.name_}")
        sys_msg = Message(role="system", action="init", content=SYSTEM_PROMPT)
        self.sys_prompt_ = SYSTEM_PROMPT
        self.history.append(sys_msg)
        #self.logger.info(sys_msg.to_log())

    def once_think(self, input: str) -> str:
        user_msg = Message(role="user", action="input", content=input)
        self.history.append(user_msg)
        prompt = self.format_to_prompt()
        response = self.llm_.invoke(prompt)
        assistant_msg = Message.convert_from_str(response)
        self.history.append(assistant_msg)
        self.logger.info("Agent思考结果：%s", assistant_msg.to_log())
        return assistant_msg.content
    
    def format_to_prompt(self) -> str:
        # 将历史消息格式化为一个字符串，作为LLM的输入提示词
        prompt = ""
        for msg in self.history:
            if hasattr(msg, 'to_prompt'):
                prompt += msg.to_prompt() + "\n"
            else:
                prompt += str(msg) + "\n"
        # 这是较为详细的调试信息，设为 debug 级别
        self.logger.debug("当前提示词：\n%s\n", prompt)
        return prompt
    
    def _think_impl(self,input:str) -> str:
        # 进行多轮思考，直到达到最大轮次或者得到final结果
        response:Message = Message(role="assistant", action="think", content="")
        for round in range(self.config_.max_rounds_):
            response = self.inner_think(input)
            if response.action == "final":
                # 仅记录最终内容，避免重复或暴露内部元信息
                #self.logger.info("当前轮次%d,Agent最终回答：%s", round+1, response.content)
                return response.content
        self.logger.info("达到最大轮次，Agent最终回答：%s", response.content)
        return response.content

    def inner_think(self,input:str) -> Message:
        # 进行一次思考，对应的返回结果按照Message格式输出
        user_msg = Message(role="user", action="input", content=input)
        self.history.append(user_msg)
        prompt = self.format_to_prompt()
        response = self.llm_.invoke(prompt)
        assistant_msg = Message.convert_from_str(response)
        self.history.append(assistant_msg)
        self.logger.debug("LLM 返回：%s", assistant_msg.to_log())
        return assistant_msg


if __name__ == "__main__":
    setup_logging()
    llm_config = LLMConfig.from_env()
    llm_client = LLMClient(llm_config)
    agent_config = AgentConfig.from_env()
    simple_agent = SimpleAgent("SimpleAgent", agent_config, llm_client)
    try:
        # ensure agent is built (SimpleAgent already sets sys prompt in __init__ but build is safe)
        simple_agent.build()
    except Exception:
        pass

    print("SimpleAgent ready. 输入 'exit' 或 'quit' 退出。")
    try:
        while True:
            try:
                user = input("输入问题> ").strip()
            except EOFError:
                break
            if not user:
                continue
            if user.lower() in ("exit", "quit"):
                break
            # single-pass think for this input
            try:
                resp = simple_agent.think(user)
            except Exception:
                simple_agent.logger.exception("SimpleAgent 调用失败")
                resp = "[agent error]"
            print("Agent回答：", resp)
    except KeyboardInterrupt:
        print("\n退出")