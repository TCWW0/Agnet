"""TODOAgent：把用户问题拆解为待办并通过 TODOTool 持久化。"""

from typing import Optional, Any, Dict
import json

from frame.core.base_agent import BaseAgent, AgentConfig
from frame.core.config import LLMConfig
from frame.core.llm import LLMClient
from frame.core.logger import Logger, Level
from frame.core.message import Message, ToolMessage, ToolResult
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool


TODO_SYS_PROMPT = (
    "你是 TODOAgent，负责把用户问题拆分成可执行待办并持久化。\n"
    "目标：围绕原问题生成短小、明确、不重复的子任务，并用 TODO 工具落库。\n"
    "权限：你只能调用 TODO 工具。\n"
    "流程：先 think 再 tool_call；拿到 tool_result 后再继续；全部成功后 final 汇总。"
)


class TODOAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        config: AgentConfig,
        llm: LLMClient,
        logger: Optional[Logger] = None,
        workflow_id: str = "todo_agent_workflow",
    ):
        m_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
        super().__init__(name, config, llm, workflow_id=workflow_id, logger=m_logger)

        self.tool_registry = ToolRegistry()
        self.tool_registry.register(TODOTool(storage_path="todo_state.json"))
        self.build()

    def init_sys_prompt(self) -> str:
        # 使用更强制性的提示：优先生成 add 操作并给出示例，避免重复 list
        msg_desc = Message.description(concise=True)
        todo_desc = TODOTool.description()
        tool_result_desc = ToolResult.description(concise=True)

        rules = [
            "首要规则：当用户请求拆分、规划或列待办时，优先直接生成若干 `add` 操作，将待办写入 TODO；不要先调用 `list` 来检测，除非用户明确要求检查现有待办。",
            "效率规则：当你已经规划出多条待办时，优先使用一次 `tool_call` 进行批量写入，而不是多轮逐条调用。",
            "响应格式：仅输出单行 action（think/tool_call/final），严格不要额外注释或多余文本。",
            "tool_call 格式：单行 JSON，只包含 `name` 与 `input`。示例：tool_call: {\"name\":\"TODO\",\"input\":{\"op\":\"add\",\"content\":\"写单元测试\"}}",
            "批量格式：tool_call: {\"name\":\"TODO\",\"input\":{\"ops\":[{\"op\":\"add\",\"content\":\"任务1\"},{\"op\":\"add\",\"content\":\"任务2\"}]}}",
            "每次响应只能包含一条 action；多步骤请使用多轮：think -> tool_call -> system/tool_result -> tool_call -> ... -> final。",
            "如模型不确定拆分条数，先输出一条简短的 `think` 提问（最多一条），然后等待用户或继续生成 add。不要同时输出 think 与 final 或多条 tool_call。",
            "当收到 system/tool_result 且 status==\"ok\" 时继续进行下一条 add；若 status!=\"ok\" 则立即输出 final 报错并停止。",
            "若执行了 `list` 且返回空（output == []），必须立即生成相应的 `add` 操作来创建待办，不要再次 `list`。",
            "仅允许调用工具：TODO；调用其它工具视为错误。",
            "始终使用中文回答，尽量简洁。",
        ]

        examples = [
            "示例流程（拆分为 3 条）：",
            "input: 帮我规划一个开发任务\n",
            "think 我将把请求拆成 3 条待办：梳理需求、设计接口、实现并自测",
            'tool_call: {"name":"TODO","input":{"ops":[{"op":"add","content":"梳理需求"},{"op":"add","content":"设计接口"},{"op":"add","content":"实现并自测"}]}}',
            'system/tool_result: {"type":"tool_result","tool_name":"TODO","status":"ok","output":{"batch":true,"total":3,"ok_count":3,"error_count":0,"results":[...]}}',
            'final 已创建 3 条待办：1.梳理需求 2.设计接口 3.实现并自测',
        ]

        parts = [
            TODO_SYS_PROMPT,
            msg_desc,
            "行为规则：",
        ]
        parts.extend(rules)
        parts.append("示例：")
        parts.extend(examples)
        parts.extend(["ToolResult 说明:", tool_result_desc, "TODOTool 说明:", todo_desc, "可用工具: TODO"]) 
        return "\n".join(parts)

    @staticmethod
    def _parse_tool_result_from_system_content(content: str) -> Optional[ToolResult]:
        """从 system/tool_result 内容中提取 ToolResult JSON。"""
        if not isinstance(content, str):
            return None
        idx = content.find("{")
        if idx < 0:
            return None
        try:
            raw = json.loads(content[idx:])
            if isinstance(raw, dict):
                return ToolResult.from_dict(raw)
        except Exception:
            return None
        return None

    @staticmethod
    def _decode_tool_call_payload(content: Any) -> Optional[Dict[str, Any]]:
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                data = json.loads(content)
                return data if isinstance(data, dict) else None
            except Exception:
                return None
        return None

    def _invoke_todo(self, payload: Dict[str, Any]) -> ToolResult:
        """执行一次 TODO 工具调用并返回 ToolResult。"""
        tool_name = payload.get("name") or payload.get("tool_name")
        tool_input = payload.get("input") if "input" in payload else payload.get("tool_input")

        if tool_name != "TODO":
            return ToolResult(
                tool_name="TODO",
                status="error",
                error_message=f"only TODO tool is allowed, got: {tool_name}",
                original_input=payload,
            )

        if isinstance(tool_input, str):
            # 允许把 JSON 字符串转换为对象；否则视为非法
            try:
                parsed = json.loads(tool_input)
                if isinstance(parsed, (dict, list)):
                    tool_input = parsed
            except Exception:
                pass

        if not isinstance(tool_input, (dict, list)):
            return ToolResult(
                tool_name="TODO",
                status="error",
                error_message="tool_call input must be an object or list (single op: {'op':...}, batch: {'ops':[...]} )",
                original_input=payload,
            )

        call_msg = ToolMessage(tool_name="TODO", tool_input=tool_input, phase="call")
        return self.tool_registry.invoke("TODO", call_msg)

    def _think_impl(self, input: str) -> str:
        user_msg = Message(role="user", action="input", content=input)
        self.append_history(user_msg)

        violation_count = 0
        max_violations = 2
        repeated_same_call = 0
        last_call_signature = ""
        last_content = ""

        for r in range(self.config_.max_rounds_):
            prompt = self.build_prompt()
            self.logger_.debug("TODOAgent 第 %d 轮 prompt:\n%s", r + 1, self.history_to_str())

            try:
                raw_resp = self.llm_.invoke(prompt)
            except Exception as e:
                self.logger_.error("TODOAgent 调用 LLM 失败: %s", str(e))
                final_err = Message(role="assistant", action="final", content=f"我无法完成该请求：调用 LLM 失败 {str(e)}")
                self.append_history(final_err)
                return final_err.content

            msgs = Message.convert_many_from_str(raw_resp)
            self.logger_.debug("TODOAgent 解析消息: %s", [str(m) for m in msgs])

            tool_call_count = 0
            has_final = False
            for m in msgs:
                if isinstance(m, ToolMessage) and m.phase == "call":
                    tool_call_count += 1
                elif getattr(m, "action", None) == "tool_call":
                    tool_call_count += 1
                if getattr(m, "action", None) == "final":
                    has_final = True

            if tool_call_count > 1 or (tool_call_count == 1 and has_final):
                violation_count += 1
                self.append_history(
                    Message(
                        role="system",
                        action="tool_error",
                        content="响应格式违规：每次仅允许一条 tool_call 或一条 final。",
                    )
                )
                if violation_count >= max_violations:
                    final_msg = Message(role="assistant", action="final", content="我无法完成该请求：模型多次输出了不合规格式。")
                    self.append_history(final_msg)
                    return final_msg.content
                continue

            for m in msgs:
                if isinstance(m, ToolMessage) and m.phase == "call":
                    payload: Dict[str, Any] = {
                        "name": m.tool_name,
                        "input": m.tool_input,
                    }
                    call_sig = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                    if call_sig == last_call_signature:
                        repeated_same_call += 1
                    else:
                        repeated_same_call = 0
                        last_call_signature = call_sig

                    if repeated_same_call >= 2:
                        self.append_history(
                            Message(
                                role="system",
                                action="tool_error",
                                content="检测到重复相同 tool_call，请修改输入后再调用。",
                            )
                        )
                        continue

                    tr = self._invoke_todo(payload)
                    res_json = tr.to_json(ensure_ascii=False)
                    nl = tr.nl or ("工具执行成功" if tr.status == "ok" else "工具执行失败")
                    self.append_history(Message(role="system", action="tool_result", content=f"{nl} {res_json}"))

                    if tr.status != "ok":
                        final_msg = Message(
                            role="assistant",
                            action="final",
                            content=f"执行失败：{tr.error_message or tr.nl or 'unknown error'}",
                        )
                        self.append_history(final_msg)
                        return final_msg.content
                    continue

                if getattr(m, "action", None) == "tool_call":
                    payload_obj = self._decode_tool_call_payload(getattr(m, "content", None))
                    if not payload_obj:
                        self.append_history(
                            Message(
                                role="system",
                                action="tool_error",
                                content="tool_call 内容必须是 JSON 对象，例如 {\"name\":\"TODO\",\"input\":{\"op\":\"list\"}}",
                            )
                        )
                        continue

                    call_sig = json.dumps(payload_obj, ensure_ascii=False, sort_keys=True)
                    if call_sig == last_call_signature:
                        repeated_same_call += 1
                    else:
                        repeated_same_call = 0
                        last_call_signature = call_sig

                    if repeated_same_call >= 2:
                        self.append_history(
                            Message(
                                role="system",
                                action="tool_error",
                                content="检测到重复相同 tool_call，请调整 input 后再调用。",
                            )
                        )
                        continue

                    tr = self._invoke_todo(payload_obj)
                    res_json = tr.to_json(ensure_ascii=False)
                    nl = tr.nl or ("工具执行成功" if tr.status == "ok" else "工具执行失败")
                    self.append_history(Message(role="system", action="tool_result", content=f"{nl} {res_json}"))

                    if tr.status != "ok":
                        final_msg = Message(
                            role="assistant",
                            action="final",
                            content=f"执行失败：{tr.error_message or tr.nl or 'unknown error'}",
                        )
                        self.append_history(final_msg)
                        return final_msg.content
                    continue

                if getattr(m, "action", None) == "think":
                    self.append_history(m)
                    continue

                if getattr(m, "action", None) == "final":
                    self.append_history(m)
                    return m.content

                self.append_history(m)
                last_content = getattr(m, "content", last_content)

        # 最大轮次兜底：从最近一次 tool_result 生成简短 final
        for h in reversed(self.history):
            if getattr(h, "role", None) == "system" and getattr(h, "action", None) == "tool_result":
                tr = self._parse_tool_result_from_system_content(getattr(h, "content", ""))
                if tr is None:
                    continue
                if tr.status == "ok":
                    final_text = f"已执行 TODO 操作成功，结果：{tr.output}"
                else:
                    final_text = f"执行失败：{tr.error_message or tr.nl or 'unknown'}"
                final_msg = Message(role="assistant", action="final", content=final_text)
                self.append_history(final_msg)
                return final_text

        return last_content


if __name__ == "__main__":
    config = AgentConfig.from_env()
    llm_config = LLMConfig.from_env()
    llm_client = LLMClient(llm_config)
    agent = TODOAgent("DemoTODOAgent", config, llm_client)

    print("TODOAgent ready. 输入 'exit' 或 'quit' 退出。")
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
            try:
                resp = agent.think(user)
            except Exception as e:
                agent.logger_.error("TODOAgent 调用失败: %s", str(e))
                resp = "[agent error]"
            print("Agent回答：", resp)
    except KeyboardInterrupt:
        print("\n退出")

    agent.logger_.info("TODOAgent 退出")
