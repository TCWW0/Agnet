"""最基础的Agent实现，只需要通过think调用底层的LLM接口输出即可"""
from typing import Optional

from frame.core.base_agent import BaseAgent
from frame.core.config import LLMConfig, AgentConfig
from frame.core.llm import LLMClient
from frame.core.prompts import SYSTEM_PROMPT
from frame.core.message import Message, ToolMessage
from frame.core.logger import Logger,Level

class SimpleAgent(BaseAgent):
    """更为规范的 SimpleAgent 实现：

    - 使用 `Message` 作为内部历史项
    - 将 prompt 发送给 LLM，解析返回为 `Message`，并按 `action` 调度
    - 全部日志使用框架内部的 `Logger`（`self.logger_`）写入核心路径
    """
    def __init__(
        self,
        name: str,
        config: AgentConfig,
        llm: LLMClient,
        workflow_id: Optional[str] = None,
        logger: Optional[Logger] = None,
    ):
        core_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
        # 将 core_logger 注入到 BaseAgent
        workflow_id = workflow_id or "666"
        super().__init__(name, config, llm, workflow_id=workflow_id, logger=core_logger)

    def _think_impl(self, input: str) -> str:
        # 将用户输入追加到历史并进行多轮交互
        user_msg = Message(role="user", action="input", content=input)
        self.append_history(user_msg)

        last_content = ""
        violation_count = 0
        VIOLATION_THRESHOLD = 2

        for r in range(self.config_.max_rounds_):
            prompt = self.build_prompt()
            # 使用核心 logger 打印关键路径日志
            self.logger_.debug("第 %d 轮 - 发送给 LLM 的 prompt:\n%s", r + 1, prompt)
            try:
                raw_resp = self.llm_.invoke(prompt)
            except Exception as e:
                self.logger_.error("调用 LLM 失败: %s", str(e))
                final_err = Message(role="assistant", action="final", content=f"我无法完成该请求：调用 LLM 失败 {str(e)}")
                self.append_history(final_err)
                return final_err.content

            self.logger_.debug("原始 LLM 响应：%s", str(raw_resp))

            parsed = Message.from_json(raw_resp)
            msgs = parsed if isinstance(parsed, list) else [parsed]

            # 合规性检查：不允许同次响应中既有 tool_call 又有 final，或有多个 tool_call
            tool_calls = [m for m in msgs if getattr(m, "action", None) == "tool_call"]
            has_final = any(getattr(m, "action", None) == "final" for m in msgs)
            if len(tool_calls) > 1 or (len(tool_calls) == 1 and has_final):
                violation_count += 1
                self.logger_.warning(
                    "检测到模型响应格式违规: tool_calls=%d, has_final=%s", len(tool_calls), has_final
                )
                self.append_history(Message(role="system", action="error", content="检测到响应格式违规，请仅返回单条 tool_call 或单条 think。"))
                if violation_count >= VIOLATION_THRESHOLD:
                    final_msg = Message(role="assistant", action="final", content="我无法完成该请求：模型多次生成不符合格式的响应。")
                    self.append_history(final_msg)
                    return final_msg.content
                continue

            # 逐条处理解析后的消息
            for m in msgs:
                # 记录解析后条目
                try:
                    self.logger_.info("解析到 LLM 消息: %s", m.to_log())
                except Exception:
                    self.logger_.info("解析到 LLM 消息: %s", str(m))

                if getattr(m, "action", None) == "tool_call":
                    # content 期望为 JSON 串，包含 name 和 input
                    # try:
                    #     payload = json.loads(m.content) if isinstance(m.content, str) else m.content
                    # except Exception:
                    #     self.logger_.error("解析 tool_call 内容为 JSON 失败: %s", str(m.content))
                    #     err = Message(role="assistant", action="final", content="我无法完成该请求：工具调用格式错误。")
                    #     self.append_history(err)
                    #     return err.content

                    # tool_name = payload.get("name") if isinstance(payload, dict) else None
                    # tool_input = payload.get("input") if isinstance(payload, dict) else payload
                    # if not tool_name:
                    #     self.logger_.error("tool_call 缺少 name 字段: %s", str(payload))
                    #     self.append_history(Message(role="system", action="error", content=f"tool_call 缺少 name 字段: {payload}"))
                    #     continue
                    self.logger_.error("SimpleAgent 当前不支持工具调用，收到 tool_call 消息: %s", str(m.content))

                elif getattr(m, "action", None) == "think":
                    # 记录内部思路，继续下一轮
                    self.append_history(m)
                elif getattr(m, "action", None) == "final":
                    self.append_history(m)
                    return m.content
                else:
                    # 未知 action，作为聊天消息追加并继续
                    self.append_history(m)
                    last_content = getattr(m, "content", "")
                    self.logger_.warning("收到未知 action 的消息，已追加到历史但未结束对话: %s", str(m))

        # 超过最大轮次，返回最后记录的内容或空字符串
        return last_content
    
    def print_format_history(self):
        str = self.build_prompt()
        self.logger_.info("当前历史消息格式化输出:\n%s", str)

if __name__ == "__main__":
    llm_config = LLMConfig.from_env()
    llm_client = LLMClient(llm_config)
    agent_config = AgentConfig.from_env()
    simple_agent = SimpleAgent(name="SimpleAgent", config=agent_config, llm=llm_client,workflow_id="simple_agent_workflow")
    # ensure agent is built (SimpleAgent already sets sys prompt in __init__ but build is safe)
    simple_agent.build()

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
                simple_agent.logger_.error("SimpleAgent 调用失败")
                resp = "[agent error]"
            print("Agent回答：", resp)
    except KeyboardInterrupt:
        print("\n退出")

    simple_agent.logger_.info("SimpleAgent 退出，当前历史消息已格式化保存至日志文件")
    simple_agent.print_format_history()