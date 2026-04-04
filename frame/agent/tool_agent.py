"""能够进行工具调用的Agent示例"""
import logging
import json

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.core.logging_config import setup_logging
from frame.tool import Calculator,ToolRegistry
from frame.core.prompts import TOOL_SYSTEM_PROMPT
from frame.core.message import Message

class ToolAgent(BaseAgent):
   def __init__(self, name: str, config: AgentConfig, llm: LLMClient):
      super().__init__(name, config, llm)
      setup_logging()
      self.logger = logging.getLogger(f"agent.{self.name_}")
      self.tool_registry = ToolRegistry()
      self.tool_registry.register(Calculator())
      prompt = TOOL_SYSTEM_PROMPT + "\n\n" + self.tool_registry.describe_all()
      sys_msg = Message(role="system", action="init", content=prompt)
      self.history.append(sys_msg)

   def _think_impl(self, input: str) -> str:
      # 进行多轮思考，同时需要能够识别中间的工具调用指令，并进行工具调用，直到达到最大轮次或者得到final结果
      msg: Message = Message(role="user", action="input", content=input)
      self.history.append(msg)
      assistant_msg: Message 
      violation_count = 0
      VIOLATION_THRESHOLD = 2    # 连续违规的容忍次数，超过后直接放弃并返回错误信息
      for round in range(self.config_.max_rounds_):
         prompt = self.convert_to_format()
         #self.logger.info("第%d轮思考开始，当前历史消息数: %d,当前的上下文: %s", round+1, len(self.history), prompt)
         response = self.llm_.invoke(prompt)
         assistant_msgs = Message.convert_many_from_str(response)

         # 先做格式合规性检测：禁止同次响应中出现多个 tool_call，或同时出现 tool_call 与 final
         tool_calls = [m for m in assistant_msgs if m.action == "tool_call"]
         has_final = any(m.action == "final" for m in assistant_msgs)
         if len(tool_calls) > 1 or (len(tool_calls) == 1 and has_final):
            violation_count += 1
            self.logger.warning("检测到模型响应违反单工具调用约束: tool_calls=%d, has_final=%s", len(tool_calls), has_final)
            # 注入系统提示，要求模型重试并只返回单行 tool_call 或 think
            err_content = (
               "检测到响应格式违规：每次响应最多允许一个独占行的 tool_call，且不能在同次响应中包含 final。"
               " 请仅返回单行 tool_call 或单行 think。"
            )
            self.history.append(Message(role="system", action="tool_error", content=err_content))
            if violation_count >= VIOLATION_THRESHOLD:
               final_msg = Message(role="assistant", action="final", content="我无法完成该请求：模型多次生成不符合格式的响应（需要单个 tool_call）。")
               self.history.append(final_msg)
               return final_msg.content
            # 让模型根据新的 system 消息重试下一轮
            continue

         # 规则按顺序处理各条消息（可能为 think / tool_call / final）
         for assistant_msg in assistant_msgs:
            if assistant_msg.action == "tool_call":
               try:
                  tool_call_info = json.loads(assistant_msg.content)
                  tool_name = tool_call_info.get("name")
                  tool_input = tool_call_info.get("input")
                  if not tool_name or not tool_input:
                     self.logger.error("工具调用指令缺少name或input字段: %s", assistant_msg.content)
                     error_msg = Message(role="system", action="tool_error", content=f"工具调用指令缺少name或input字段: {assistant_msg.content}")
                     self.history.append(error_msg)
                     continue
                  tool_result = self.execute_tool(tool_name, tool_input)
                  tool_result_msg = Message(role="system", action="tool_result", content=tool_result)
                  self.history.append(tool_result_msg)
               except json.JSONDecodeError:
                  self.logger.error("解析工具调用指令失败，内容不是合法的JSON: %s", assistant_msg.content)
                  final_msg = Message(role="assistant", action="final", content=f"我无法完成该请求：工具调用指令格式错误。")
                  self.history.append(final_msg)
                  return final_msg.content
            elif assistant_msg.action == "think":
               self.history.append(assistant_msg)
               # TODO：后续可以根据think内容来进行记忆的更新或者RAG注入等等
            elif assistant_msg.action == "final":
               self.history.append(assistant_msg)
               return assistant_msg.content
      # 达到最大轮次，仍未得到final结果，返回最后一次思考的内容作为最终结果
      return assistant_msg.content #type: ignore

   def convert_to_format(self) -> str:
      # 将历史信息格式化为一个字符串，作为LLM的输入提示词
      prompt = ""
      for msg in self.history:
         if hasattr(msg, 'to_prompt'):
            prompt += msg.to_prompt() + "\n"
         else:
            prompt += str(msg) + "\n"
      self.logger.debug(f"当前提示词: {prompt}")
      return prompt
   
   def execute_tool(self, tool_name: str, tool_input: str) -> str:
      tool = self.tool_registry.get(tool_name)
      if not tool:
         self.logger.error("未找到工具: %s", tool_name)
         return f"Error: Tool '{tool_name}' not found."
      try:
         res = tool.run(tool_input)
         self.logger.info("工具 %s 执行结果: %s", tool_name, res)
         return res
      except Exception as e:
         self.logger.error("工具 %s 执行失败: %s", tool_name, str(e))
         return f"Error: Tool '{tool_name}' execution failed: {str(e)}"
      
      
if __name__ == "__main__":
   config = AgentConfig(max_rounds=10)
   llm_config = LLMConfig.from_env()
   llm_client = LLMClient(llm_config)
   agent = ToolAgent("DemoToolAgent", config, llm_client)
   user_input = "请帮我计算一下 12 除以 4 的结果。"   
   final_answer = agent.think(user_input)
   print("最终回答:", final_answer)