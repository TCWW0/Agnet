"""能够进行工具调用的 Agent（与新 ToolResult/ToolRegistry 协议兼容）。

设计要点：
- 使用 `ToolRegistry.invoke()` 执行工具，保证该层返回 JSON 字符串（ToolResult 协议）。
- 将工具返回作为系统消息追加到历史（action="tool_result"，content 为 JSON 字符串）。
- 支持两种工具调用输入：`ToolMessage`（phase=="call"）或 `Message`（action=="tool_call" 且 content 为 JSON 字符串）。
"""
from typing import Optional, List
import json

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig, LLMConfig
from frame.core.llm import LLMClient
from frame.tool import Calculator, ToolRegistry
from frame.core.prompts import TOOL_SYSTEM_PROMPT
from frame.core.message import Message, ToolMessage
from frame.core.logger import Logger, Level


class ToolAgent(BaseAgent):
   def __init__(
      self,
      name: str,
      config: AgentConfig,
      llm: LLMClient,
      tool_registry: Optional[ToolRegistry] = None,
      workflow_id: Optional[str] = None,
      logger: Optional[Logger] = None,
   ):
      core_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
      super().__init__(name, config, llm, workflow_id=workflow_id or "tool_agent_workflow", logger=core_logger)

      # 注册工具（如果外部没有传入 registry，则使用默认）
      self.tool_registry = tool_registry or ToolRegistry()
      # 默认示例工具
      if "Calculator" not in self.tool_registry.list_tools():
         self.tool_registry.register(Calculator())

      # 构建并设置系统提示词（包含工具列表），但不要把它作为历史消息重复添加
      self.build()

   def init_sys_prompt(self) -> str:
      # 只注入可用工具名称以降低 token 消耗，具体描述可按需查询
      tools = self.tool_registry.list_tools()
      tools_line = ", ".join(tools) if tools else "(无可用工具)"
      return TOOL_SYSTEM_PROMPT + "\n\n可用工具: " + tools_line

   def _think_impl(self, input: str) -> str:
      # 追加用户输入到历史
      user_msg = Message(role="user", action="input", content=input)
      self.append_history(user_msg)

      violation_count = 0
      VIOLATION_THRESHOLD = 2
      last_content = ""

      for r in range(self.config_.max_rounds_):
         prompt = self.build_prompt()
         self.logger_.debug("第 %d 轮 - 发送给 LLM 的 prompt:\n%s", r + 1, self.history_to_str())

         try:
            raw_resp = self.llm_.invoke(prompt)
         except Exception as e:
            self.logger_.error("调用 LLM 失败: %s", str(e))
            final_err = Message(role="assistant", action="final", content=f"我无法完成该请求：调用 LLM 失败 {str(e)}")
            self.append_history(final_err)
            return final_err.content

         # support both JSON and action-line formatted outputs from LLM
         msgs = Message.convert_many_from_str(raw_resp)
         self.logger_.debug("解析后的消息列表：%s", [str(m) for m in msgs])

         # 合规性检查：不允许同次响应中既有 tool_call 又有 final，或有多个 tool_call
         tool_call_count = 0
         has_final = False
         for m in msgs:
            if isinstance(m, ToolMessage) and getattr(m, "phase", None) == "call":
               tool_call_count += 1
            if getattr(m, "action", None) == "tool_call":
               tool_call_count += 1
            if getattr(m, "action", None) == "final":
               has_final = True

         if tool_call_count > 1 or (tool_call_count == 1 and has_final):
            violation_count += 1
            self.logger_.warning("检测到模型响应格式违规: tool_call_count=%d, has_final=%s", tool_call_count, has_final)
            err = Message(role="system", action="tool_error", content="检测到响应格式违规：请仅返回单条 tool_call 或单条 think。")
            self.append_history(err)
            if violation_count >= VIOLATION_THRESHOLD:
               final_msg = Message(role="assistant", action="final", content="我无法完成该请求：模型多次生成不符合格式的响应。")
               self.append_history(final_msg)
               return final_msg.content
            continue

         # 逐条处理 LLM 返回消息
         for m in msgs:
            # 记录解析后条目
            # try:
            #    self.logger_.info("解析到 LLM 消息: %s", m.to_log())
            # except Exception:
            #    self.logger_.info("解析到 LLM 消息: %s", str(m))

            # 工具调用：支持 ToolMessage（phase==call）或 Message(action==tool_call 且 content 为 JSON)
            if isinstance(m, ToolMessage) and m.phase == "call":
               tool_name = m.tool_name
               tool_input = m.tool_input if isinstance(m.tool_input, str) else json.dumps(m.tool_input, ensure_ascii=False)
               try:
                  res_json = self.tool_registry.invoke(tool_name, tool_input)
                  # 把自然语言摘要放在前面，后面跟上原始 JSON 响应（单行）以便模型更容易识别工具结果
                  try:
                     tr = json.loads(res_json)
                     nl = tr.get("nl") if isinstance(tr, dict) else None
                  except Exception:
                     nl = None
                  content = f"{nl} {res_json}" if nl else res_json
                  self.append_history(Message(role="system", action="tool_result", content=content))
               except Exception as e:
                  self.logger_.error("工具调用失败: %s", str(e))
                  self.append_history(Message(role="system", action="tool_error", content=str(e)))

            elif getattr(m, "action", None) == "tool_call":
               # m.content 期望为 JSON 字符串，包含 name 和 input
               try:
                  payload = json.loads(m.content) if isinstance(m.content, str) else m.content
               except Exception:
                  self.logger_.error("解析 tool_call 内容为 JSON 失败: %s", str(m.content))
                  final_msg = Message(role="assistant", action="final", content="我无法完成该请求：工具调用指令格式错误。")
                  self.append_history(final_msg)
                  return final_msg.content

               tool_name = payload.get("name") or payload.get("tool_name")
               tool_input = payload.get("input") or payload.get("tool_input")
               if not tool_name:
                  self.logger_.error("tool_call 缺少 name 字段: %s", str(payload))
                  self.append_history(Message(role="system", action="tool_error", content=f"tool_call 缺少 name 字段: {payload}"))
                  continue

               try:
                  res_json = self.tool_registry.invoke(tool_name, tool_input)
                  try:
                     tr = json.loads(res_json)
                     nl = tr.get("nl") if isinstance(tr, dict) else None
                  except Exception:
                     nl = None
                  content = f"{nl} {res_json}" if nl else res_json
                  self.append_history(Message(role="system", action="tool_result", content=content))
               except Exception as e:
                  self.logger_.error("工具调用失败: %s", str(e))
                  self.append_history(Message(role="system", action="tool_error", content=str(e)))

            elif getattr(m, "action", None) == "think":
               self.append_history(m)

            elif getattr(m, "action", None) == "final":
               self.append_history(m)
               return m.content

            else:
               # 未知 action：作为聊天/记录追加
               self.append_history(m)
               last_content = getattr(m, "content", last_content)

      # 达到最大轮次，仍未得到 final
      # 回退策略：如果历史中存在最近的 tool_result（系统消息），解析并合成一个简单的 final 返回，避免空响应
      for h in reversed(self.history):
         try:
            if getattr(h, "role", None) == "system" and getattr(h, "action", None) == "tool_result":
               # content 是 ToolRegistry.invoke 返回的单行 JSON
               try:
                  tr = json.loads(h.content) if isinstance(h.content, str) else h.content
               except Exception:
                  tr = None
               if isinstance(tr, dict):
                  status = tr.get("status")
                  if status == "ok":
                     out = tr.get("output")
                     final_text = str(out)
                  else:
                     final_text = f"我无法完成该请求：工具执行失败: {tr.get('error_message') or tr.get('error_code') or 'unknown'}"
                  final_msg = Message(role="assistant", action="final", content=final_text)
                  self.append_history(final_msg)
                  return final_text
         except Exception:
            continue

      return last_content


if __name__ == "__main__":
   config = AgentConfig(max_rounds=10)
   llm_config = LLMConfig.from_env()
   llm_client = LLMClient(llm_config)
   agent = ToolAgent("DemoToolAgent", config, llm_client)

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
               resp = agent.think(user)
         except Exception:
               agent.logger_.error("ToolAgent 调用失败")
               resp = "[agent error]"
         print("Agent回答：", resp)
   except KeyboardInterrupt:
        print("\n退出")

   agent.logger_.info("ToolAgent 退出，当前历史消息已格式化保存至日志文件")