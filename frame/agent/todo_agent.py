"""TODOAgent：把用户问题拆解为待办并通过 TODOTool 持久化。"""

from typing import Optional, Any, Dict, List
import json
import uuid

from frame.core.base_agent import BaseAgent, AgentConfig
from frame.core.config import LLMConfig
from frame.core.llm import LLMClient
from frame.core.logger import Logger, Level
from frame.core.message import Message, ToolMessage, ToolResult
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool


TODO_SYS_PROMPT = (
    "你是 TODOAgent，负责把任意用户输入拆分成可执行待办并持久化。\n"
    "目标：无论输入是知识问答、解释、比较、调研、排错、设计、总结还是普通任务，都必须拆成短小、明确、不重复的子任务，并用 TODO 工具落库。\n"
    "权限：你只能调用 TODO 工具。\n"
    "硬性约束：不要直接回答原问题，不要拒绝拆解，不要把问题推回给用户；如果是知识问答，也要拆成“理解概念、分点解释、举例说明、总结注意事项”这类待办。\n"
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
        todo_tool: Optional[TODOTool] = None,
    ):
        m_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
        super().__init__(name, config, llm, workflow_id=workflow_id, logger=m_logger)

        self.last_plan_id_: Optional[str] = None
        self._plan_order_counter_: int = 0
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(todo_tool or TODOTool(storage_path="todo_state.json"))
        self.build()

    def init_sys_prompt(self) -> str:
        # 使用更强制性的提示：无论输入类型都必须拆解，并给出知识问答示例
        msg_desc = Message.description(concise=True)
        todo_desc = TODOTool.description()
        tool_result_desc = ToolResult.description(concise=True)

        rules = [
            "首要规则：无论输入是知识问答、解释、比较、调研、排错、设计、总结还是普通任务，都必须拆成待办；不要直接回答，也不要判断‘不需要拆解’。",
            "首要规则：优先直接生成若干 `add` 操作，将待办写入 TODO；不要先调用 `list` 来检测，除非用户明确要求检查现有待办。",
            "效率规则：当你已经规划出多条待办时，优先使用一次 `tool_call` 进行批量写入，而不是多轮逐条调用。",
            "响应格式：仅输出单行 action（think/tool_call/final），严格不要额外注释或多余文本。",
            "tool_call 格式：单行 JSON，只包含 `name` 与 `input`。示例：tool_call: {\"name\":\"TODO\",\"input\":{\"op\":\"add\",\"content\":\"写单元测试\"}}",
            "批量格式：tool_call: {\"name\":\"TODO\",\"input\":{\"ops\":[{\"op\":\"add\",\"content\":\"任务1\"},{\"op\":\"add\",\"content\":\"任务2\"}]}}",
            "每次响应只能包含一条 action；多步骤请使用多轮：think -> tool_call -> system/tool_result -> tool_call -> ... -> final。",
            "如模型不确定拆分条数，先输出一条简短的 `think` 思路（最多一条），然后继续生成 add。不要同时输出 think 与 final 或多条 tool_call。",
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
            "示例流程（知识问答也要拆解）：",
            "input: 请给我介绍一下C++中的智能指针",
            "think 我将把问题拆成理解概念、说明 unique_ptr、说明 shared_ptr、总结注意事项 4 条待办",
            'tool_call: {"name":"TODO","input":{"ops":[{"op":"add","content":"理解智能指针的核心概念"},{"op":"add","content":"说明 unique_ptr 的所有权语义"},{"op":"add","content":"说明 shared_ptr 与 weak_ptr 的作用"},{"op":"add","content":"总结使用场景与注意事项"}]}}',
            'final 已创建 4 条待办：1.理解智能指针的核心概念 2.说明 unique_ptr 的所有权语义 3.说明 shared_ptr 与 weak_ptr 的作用 4.总结使用场景与注意事项',
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

    # 从被包装成Json的字符流中解析出其中的 objective，source 字段，处理为一个本类中使用的对象
    # input_text 实际上应该是一个Json序列化后的字符串，具体查看DeepThoughtAgent._build_plan_request
    @staticmethod
    def _parse_planning_request(input_text: str) -> Dict[str, Any]:
        req: Dict[str, Any] = {
            "objective": input_text,
            "source": "user",
        }
        if not isinstance(input_text, str):
            return req

        text = input_text.strip()
        if not text:
            return req

        try:
            raw = json.loads(text)
        except Exception:
            return req

        if not isinstance(raw, dict):
            return req

        objective = raw.get("objective") or raw.get("query") or raw.get("input")
        if isinstance(objective, str) and objective.strip():
            req["objective"] = objective.strip()

        source = raw.get("source")
        if isinstance(source, str) and source.strip():
            req["source"] = source.strip()

        return req

    @staticmethod
    def _build_planning_prompt(objective: str, source: str) -> str:
        return (
            "【强制通用拆解模式】\n"
            f"输入来源：{source}\n"
            "你必须把下面的输入拆解成 2 到 5 条可执行待办。\n"
            "无论输入是知识问答、解释、比较、调研、排错、设计、总结或任务描述，都必须拆解；不要直接回答，不要拒绝拆解。\n"
            "输出优先使用批量 add；子任务要短小、明确、可执行，避免重复。\n"
            "如果是知识问答，优先拆成理解概念、分点解释、举例说明、总结注意事项。\n"
            "原始输入：\n"
            f"{objective}"
        )

    @staticmethod
    def _payload_has_add(tool_input: Any) -> bool:
        if isinstance(tool_input, dict):
            if str(tool_input.get("op") or "").lower() == "add":
                return True
            ops = tool_input.get("ops")
            if isinstance(ops, list):
                return any(isinstance(one, dict) and str(one.get("op") or "").lower() == "add" for one in ops)
        if isinstance(tool_input, list):
            return any(isinstance(one, dict) and str(one.get("op") or "").lower() == "add" for one in tool_input)
        return False

    @staticmethod
    def _looks_like_direct_refusal(content: str) -> bool:
        text = " ".join(str(content).split())
        keywords = [
            "无需生成待办",
            "不需要生成待办",
            "无需拆解",
            "不需要拆解",
            "这是知识问答",
            "可以直接回答",
            "直接回答",
            "无需待办",
            "请直接回答",
            "您可以直接回答",
        ]
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _build_fallback_tasks(objective: str) -> List[str]:
        return [
            "梳理原始问题与目标",
            "拆解关键概念或子问题",
            "形成最终结论并复核",
        ]

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

    # 将LLM回答的 tool_call 后面跟着的文本使用Json解析成一个字典对象
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

    def _merge_plan_metadata(self, metadata: Any, objective: Optional[str], plan_id: Optional[str], source: Optional[str] = None) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(metadata) if isinstance(metadata, dict) else {}
        if "workflow_id" not in merged:
            merged["workflow_id"] = self.workflow_id_
        if plan_id and "plan_id" not in merged:
            merged["plan_id"] = plan_id
        if objective and "objective" not in merged:
            merged["objective"] = objective
        if "source" not in merged:
            merged["source"] = source or "todo_agent"
        if "order" not in merged:
            self._plan_order_counter_ += 1
            merged["order"] = self._plan_order_counter_
        return merged

    def _inject_plan_context(self, tool_input: Any, objective: Optional[str], plan_id: Optional[str], source: Optional[str] = None) -> Any:
        """为 add 操作注入 workflow/plan/objective 元数据。"""
        if plan_id is None:
            return tool_input

        if isinstance(tool_input, dict):
            op = str(tool_input.get("op") or "").lower()
            if op == "add":
                enriched = dict(tool_input)
                enriched["metadata"] = self._merge_plan_metadata(enriched.get("metadata"), objective, plan_id, source=source)
                return enriched

            raw_ops = tool_input.get("ops")
            if isinstance(raw_ops, list):
                new_ops = []
                for one in raw_ops:
                    if not isinstance(one, dict):
                        new_ops.append(one)
                        continue
                    if str(one.get("op") or "").lower() == "add":
                        one2 = dict(one)
                        one2["metadata"] = self._merge_plan_metadata(one2.get("metadata"), objective, plan_id, source=source)
                        new_ops.append(one2)
                    else:
                        new_ops.append(one)
                enriched = dict(tool_input)
                enriched["ops"] = new_ops
                return enriched

        if isinstance(tool_input, list):
            new_ops = []
            for one in tool_input:
                if not isinstance(one, dict):
                    new_ops.append(one)
                    continue
                if str(one.get("op") or "").lower() == "add":
                    one2 = dict(one)
                    one2["metadata"] = self._merge_plan_metadata(one2.get("metadata"), objective, plan_id, source=source)
                    new_ops.append(one2)
                else:
                    new_ops.append(one)
            return new_ops

        return tool_input

    def _invoke_todo(self, payload: Dict[str, Any], objective: Optional[str] = None, plan_id: Optional[str] = None, source: Optional[str] = None) -> ToolResult:
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

        tool_input = self._inject_plan_context(tool_input, objective=objective, plan_id=plan_id, source=source)
        call_msg = ToolMessage(tool_name="TODO", tool_input=tool_input, phase="call")
        return self.tool_registry.invoke("TODO", call_msg)

    def _think_impl(self, input: str) -> str:
        request = self._parse_planning_request(input)
        objective = str(request.get("objective") or input).strip()  # 获取用户输入原文
        source = str(request.get("source") or "user").strip() or "user"
        planning_prompt = self._build_planning_prompt(objective, source)    # 使用提示词强制要求LLM拆解用户输入

        user_msg = Message(role="user", action="input", content=planning_prompt)
        self.append_history(user_msg)

        self.last_plan_id_ = uuid.uuid4().hex[:12]
        self._plan_order_counter_ = 0
        self.logger_.info("TODOAgent 开始通用拆解，workflow_id=%s，plan_id=%s，source=%s", self.workflow_id_, self.last_plan_id_, source)

        violation_count = 0             # 违规计数器：每次输出不合规格式（如同时输出多条 tool_call 或 final）就加1，达到上限则强制终止并输出错误 final
        max_violations = 2
        repeated_same_call = 0
        last_call_signature = ""
        last_content = ""
        created_any_task = False

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

                    self.logger_.info("TODOAgent 调用工具，plan_id=%s", self.last_plan_id_)
                    tr = self._invoke_todo(payload, objective=objective, plan_id=self.last_plan_id_, source=source)
                    res_json = tr.to_json(ensure_ascii=False)
                    nl = tr.nl or ("工具执行成功" if tr.status == "ok" else "工具执行失败")
                    self.append_history(Message(role="system", action="tool_result", content=f"{nl} {res_json}"))
                    self.logger_.info("TODOAgent 工具结果 status=%s", tr.status)
                    if tr.status == "ok" and self._payload_has_add(m.tool_input):
                        created_any_task = True

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

                    self.logger_.info("TODOAgent 调用工具，plan_id=%s", self.last_plan_id_)
                    tool_input = payload_obj.get("input") if "input" in payload_obj else payload_obj.get("tool_input")
                    tr = self._invoke_todo(payload_obj, objective=objective, plan_id=self.last_plan_id_, source=source)
                    res_json = tr.to_json(ensure_ascii=False)
                    nl = tr.nl or ("工具执行成功" if tr.status == "ok" else "工具执行失败")
                    self.append_history(Message(role="system", action="tool_result", content=f"{nl} {res_json}"))
                    self.logger_.info("TODOAgent 工具结果 status=%s", tr.status)
                    if tr.status == "ok" and self._payload_has_add(tool_input):
                        created_any_task = True

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
                    if not created_any_task:
                        refusal_text = str(getattr(m, "content", "") or "")
                        self.logger_.warning("TODOAgent 检测到直接 final 且尚未拆解，准备重试/兜底：%s", refusal_text)
                        violation_count += 1
                        self.append_history(
                            Message(
                                role="system",
                                action="tool_error",
                                content="不要直接回答；无论输入类型都必须拆解成待办，并至少输出一条 TODO add 操作。",
                            )
                        )
                        if violation_count >= max_violations:
                            break
                        continue
                    self.append_history(m)
                    self.logger_.info("TODOAgent 规划结束，plan_id=%s", self.last_plan_id_)
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
                self.logger_.info("TODOAgent 规划结束（兜底），plan_id=%s", self.last_plan_id_)
                return final_text

        if not created_any_task:
            fallback_tasks = self._build_fallback_tasks(objective)
            self.logger_.warning("TODOAgent 未生成待办，触发通用兜底拆解，plan_id=%s", self.last_plan_id_)
            fallback_payload = {
                "name": "TODO",
                "input": {
                    "ops": [{"op": "add", "content": task} for task in fallback_tasks],
                },
            }
            tr = self._invoke_todo(fallback_payload, objective=objective, plan_id=self.last_plan_id_, source=source)
            if tr.status == "ok":
                final_text = f"已基于原始输入生成 {len(fallback_tasks)} 条通用待办：1.{fallback_tasks[0]} 2.{fallback_tasks[1]} 3.{fallback_tasks[2]}"
                self.append_history(Message(role="assistant", action="final", content=final_text))
                self.logger_.info("TODOAgent 规划结束（通用兜底），plan_id=%s", self.last_plan_id_)
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
