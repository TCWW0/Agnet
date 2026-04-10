"""
一个专门用于提取一个TODOTool中表项并进行执行的Agent
其某种程度上可以看做是在规划阶段后来进行执行的Agent，或者说一个专门用于执行现有的TODOPlan的Agent
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.logger import Logger, Level
from frame.core.message import Message, ToolMessage, ToolResult
from frame.tool.todo import TODOTool
from frame.tool.registry import ToolRegistry

# 这里的设计思路是，由Agent内部的规则来检索一条合适的任务来提供执行，减少对于上下文的污染
EXECUTE_PROMPT_TEMPLATE = """你是执行代理，请完成当前子任务。
你将看到总体目标、计划摘要以及最近完成结果，用于避免重复回答。

总体目标：
{objective}

计划摘要：
{plan_summary}

最近完成结果：
{recent_results}

当前任务（#{item_id}）：
{item_content}

输出要求：
1. 你可以进行多轮思考，每轮仅输出一条 action（think 或 final）。
2. 当你尚未准备好最终答案时输出：think <你的中间思考>。
3. 当你准备结束时输出：final <执行结果>。
4. 执行结果应尽量具体，且不要与最近结果机械重复。
"""

PROCESS_SYS_PROMPT = (
    "你是 ProcessAgent，负责执行 TODO 任务。\n"
    "严格输出单行 action 内容，action 只允许 think 或 final。\n"
    "不要输出 tool_call，不要输出多行，不要输出额外解释。\n"
    "若信息不足，先 think 再在后续轮次给出 final。"
)

class ProcessAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        config: AgentConfig,
        llm: LLMClient,
        workflow_id: str = "process_agent_workflow",
        logger: Optional[Logger] = None,
        todo_tool: Optional[TODOTool] = None,
        recent_results_limit: int = 5,
    ):
        # 这里对于日志类实际上是期望传入的，否则在逻辑上对应的日志记录是分散的，不利于后续对于整个思考流程的观察和分析
        logger = logger if logger is not None else Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
        assert todo_tool is not None, "ProcessAgent requires a TODOTool instance"

        self.todo_tool_ = todo_tool
        self.recent_results_limit_ = max(1, int(recent_results_limit))
        self.tool_registry_ = ToolRegistry()
        self.tool_registry_.register(todo_tool)
        super().__init__(name, config, llm, workflow_id, logger)
        self.build()

    # 注入基本的消息格式
    def init_sys_prompt(self) -> str:
        return PROCESS_SYS_PROMPT

    def _invoke_todo(self, tool_input: Dict[str, Any]) -> ToolResult:
        msg = ToolMessage(tool_name="TODO", tool_input=tool_input, phase="call")
        return self.tool_registry_.invoke("TODO", msg)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(str(text).strip().split()).lower()
    
    """原始期望Json格式实例：
    {
        "objective": "总体目标文本",
        "plan_id": "必选的计划ID，用于识别当前执行的计划，是保证整个工作流为一个逻辑整体的关键
    }
    """
    def _parse_request(self, input_text: str) -> Dict[str, Any]:
        req: Dict[str, Any] = {
            "objective": input_text,
            "plan_id": None,
            "item_id": None,
        }
        if not isinstance(input_text, str):
            return req

        text = input_text.strip()
        if not text:
            return req

        try:
            obj = json.loads(text)
        except Exception:
            return req

        if not isinstance(obj, dict):
            return req

        objective = obj.get("objective") or obj.get("query") or obj.get("input")
        if isinstance(objective, str) and objective.strip():
            req["objective"] = objective.strip()

        plan_id = obj.get("plan_id")
        if isinstance(plan_id, str) and plan_id.strip():
            req["plan_id"] = plan_id.strip()

        item_id = obj.get("item_id")
        if item_id is not None:
            try:
                req["item_id"] = int(item_id)
            except Exception:
                req["item_id"] = None
        return req

    # 从TODO中获取所有的表项，并获取本工作流中属于同一个计划的表项，记录工作流下的所有Item
    def _list_plan_items(self, plan_id: Optional[str] = None) -> List[Dict[str, Any]]:
        tr = self._invoke_todo({"op": "list"})
        if tr.status != "ok" or not isinstance(tr.output, list):
            return []

        items = [it for it in tr.output if isinstance(it, dict)]
        if plan_id:
            selected: List[Dict[str, Any]] = []
            for it in items:
                meta = it.get("metadata")
                if isinstance(meta, dict) and meta.get("plan_id") == plan_id:
                    selected.append(it)
            items = selected

        items.sort(key=lambda x: int(x.get("id", 0) or 0))
        return items

    # 获取规则：优先选择指定 item_id 的任务；否则选择第一个状态为 PENDING 的任务；如果没有待执行任务则返回 None
    def _select_next_item(self, items: List[Dict[str, Any]], item_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if item_id is not None:
            for it in items:
                try:
                    if int(it.get("id", 0) or 0) != int(item_id):
                        continue
                    status = str(it.get("status", "") or "").upper()
                    if status in ("COMPLETED", "CANCELLED"):
                        return None
                    return it
                except Exception:
                    continue
            return None

        for it in items:
            status = str(it.get("status", "") or "").upper()
            if status == "PENDING":
                return it
        return None

    """
    上下文中包含多个信息：总体目标、计划摘要、最近完成结果、当前任务内容等
    放入这些信息的需求是将来可能的执行过程中，模型可能会需要回顾这些信息来进行思考和决策，同时也可以通过提供最近完成结果来避免模型给出与之前结果机械重复的回答
    目前的设计是把这些信息都放在一个文本块中，未来也可以考虑更结构化的方式来提供这些信息，或者提供不同的提示词来引导模型关注不同的信息
    TODO: 使用更加优雅的上下文构建策略，对于每个任务通过context engineering的方式来构建不同的上下文，或者提供不同的提示词来引导模型关注不同的信息
    """
    def build_context(
        self,
        objective: str,
        plan_items: List[Dict[str, Any]],
        current_item: Dict[str, Any],
    ) -> Dict[str, str]:
        """构建单任务执行上下文，便于后续替换为不同策略。"""
        cur_id = int(current_item.get("id", 0) or 0)
        meta_any = current_item.get("metadata")
        current_meta: Dict[str, Any] = meta_any if isinstance(meta_any, dict) else {}
        resolved_objective = objective or str(current_meta.get("objective") or "") or "(未提供总体目标)"

        plan_rows: List[str] = []
        for it in plan_items:
            item_id = int(it.get("id", 0) or 0)
            status = str(it.get("status", "") or "")
            content = str(it.get("content", "") or "")
            plan_rows.append(f"- #{item_id} [{status}] {content}")
        if not plan_rows:
            plan_rows = ["(空计划)"]

        # 最近结果：从其它条目的 responses 中摘取最后一条
        recent: List[str] = []
        for it in plan_items:
            item_id = int(it.get("id", 0) or 0)
            if item_id == cur_id:
                continue
            responses = it.get("responses")
            if not isinstance(responses, list) or not responses:
                continue
            last = responses[-1]
            if not isinstance(last, dict):
                continue
            text = str(last.get("content", "") or "").strip()
            if not text:
                continue
            snippet = text.replace("\n", " ")
            if len(snippet) > 100:
                snippet = snippet[:97] + "..."
            recent.append(f"- #{item_id}: {snippet}")
        if recent:
            recent = recent[-self.recent_results_limit_:]
        else:
            recent = ["(暂无)"]

        # 用于EXECUTE_PROMPT_TEMPLATE的注入
        return {
            "objective": resolved_objective,
            "plan_summary": "\n".join(plan_rows),
            "recent_results": "\n".join(recent),
            "item_id": str(cur_id),
            "item_content": str(current_item.get("content", "") or ""),
        }

    def _run_llm_until_final(self, context: Dict[str, str]) -> str:
        user_prompt = EXECUTE_PROMPT_TEMPLATE.format(**context)
        local_history: List[Message] = [Message(role="user", action="input", content=user_prompt)]

        violation_count = 0
        last_think = ""
        repeat_think_count = 0

        for _ in range(self.config_.max_rounds_):
            lines: List[str] = [self.sys_prompt_ or PROCESS_SYS_PROMPT]
            lines.extend([m.to_prompt() for m in local_history])
            prompt = "\n".join(lines)

            try:
                raw_resp = self.llm_.invoke(prompt)
            except Exception as e:
                return f"执行失败：调用LLM异常：{str(e)}"

            msgs = Message.convert_many_from_str(raw_resp)
            if not msgs:
                local_history.append(Message(role="system", action="error", content="模型未返回有效消息，请输出 final。"))
                continue

            tool_call_count = 0
            final_count = 0
            for m in msgs:
                if isinstance(m, ToolMessage) or getattr(m, "action", None) == "tool_call":
                    tool_call_count += 1
                if getattr(m, "action", None) == "final":
                    final_count += 1

            # 约束：不能调用工具；每轮至多一个 final
            if tool_call_count > 0 or final_count > 1:
                violation_count += 1
                local_history.append(
                    Message(
                        role="system",
                        action="error",
                        content="格式违规：ProcessAgent 仅允许 think/final 且每轮最多一个 final。",
                    )
                )
                if violation_count >= 2:
                    return "执行未完成：模型多次输出不合规格式，已使用兜底结果。"
                continue

            for m in msgs:
                action = getattr(m, "action", None)
                if action == "final":
                    content = str(getattr(m, "content", "") or "").strip()
                    return content if content else "执行完成，但未返回具体结果。"

                if action == "think":
                    text = str(getattr(m, "content", "") or "").strip()
                    if not text:
                        continue
                    local_history.append(Message(role="assistant", action="think", content=text))
                    if text == last_think:
                        repeat_think_count += 1
                    else:
                        repeat_think_count = 0
                        last_think = text

                else:
                    # 把未知输出当作 think 处理，并在下一轮继续逼近 final
                    text = str(getattr(m, "content", "") or "").strip() or str(raw_resp).strip()
                    if text:
                        local_history.append(Message(role="assistant", action="think", content=text))

            if repeat_think_count >= 2:
                return "执行未完成：模型反复输出相同思路，已使用兜底结果。"

        return "执行未完成：达到最大思考轮次，已使用兜底结果。"

    def _append_response_and_complete(self, item: Dict[str, Any], result_text: str, plan_id: Optional[str]) -> None:
        item_id = int(item.get("id", 0) or 0)
        if item_id <= 0:
            return

        # 轻量去重：若与已有最后结果相同，打标签而不阻断完成
        duplicate_of: Optional[int] = None
        all_items = self._list_plan_items(plan_id)
        current_norm = self._normalize_text(result_text)
        for it in all_items:
            oid = int(it.get("id", 0) or 0)
            if oid == item_id:
                continue
            responses = it.get("responses")
            if not isinstance(responses, list) or not responses:
                continue
            last = responses[-1]
            if not isinstance(last, dict):
                continue
            other_text = str(last.get("content", "") or "")
            if current_norm and current_norm == self._normalize_text(other_text):
                duplicate_of = oid
                break

        self._invoke_todo(
            {
                "op": "add_response",
                "id": item_id,
                "response": result_text,
                "by": self.name_,
                "metadata": {
                    "executor": self.name_,
                    "workflow_id": self.workflow_id_,
                    "plan_id": plan_id,
                    "duplicate_of": duplicate_of,
                    "executed_at": datetime.now().isoformat(),
                },
            }
        )

        self._invoke_todo(
            {
                "op": "update",
                "id": item_id,
                "status": "COMPLETED",
                "metadata": {
                    "executor": self.name_,
                    "workflow_id": self.workflow_id_,
                    "plan_id": plan_id,
                    "last_executed_at": datetime.now().isoformat(),
                    "duplicate_of": duplicate_of,
                },
            }
        )

    def _think_impl(self, input: str) -> str:
        req = self._parse_request(input)
        objective = str(req.get("objective") or "").strip()
        plan_id = req.get("plan_id")
        item_id = req.get("item_id")    # 可选的 item_id 参数允许直接指定要执行的任务，否则默认选择第一个待执行的任务

        self.logger_.info(
            "ProcessAgent 开始执行，workflow_id=%s，plan_id=%s，item_id=%s",
            self.workflow_id_,
            plan_id,
            item_id,
        )

        self.append_history(Message(role="user", action="input", content=input))

        items = self._list_plan_items(plan_id)
        self.logger_.info("ProcessAgent 读取任务 %d 条", len(items))
        if not items:
            final = "未找到可执行的 TODO 任务。"
            self.append_history(Message(role="assistant", action="final", content=final))
            self.logger_.info("ProcessAgent 结束：无可执行任务")
            return final

        item = self._select_next_item(items, item_id=item_id)
        if item is None:
            final = "当前没有待执行任务（可能已全部完成或已取消）。"
            self.append_history(Message(role="assistant", action="final", content=final))
            self.logger_.info("ProcessAgent 结束：无待执行任务")
            return final

        # 简单的逻辑上的锁，实际上可能并不安全，并发安全性之后再讨论吧 TODO
        cur_id = int(item.get("id", 0) or 0)
        self.logger_.info("ProcessAgent 选择任务 id=%s content=%s", cur_id, item.get("content"))
        claim_tr = self._invoke_todo({"op": "claim", "id": cur_id, "by": self.name_})
        if claim_tr.status != "ok":
            msg = claim_tr.error_message or claim_tr.nl or "claim失败"
            final = f"任务#{cur_id} 领取失败：{msg}"
            self.append_history(Message(role="assistant", action="final", content=final))
            self.logger_.warning("ProcessAgent 任务领取失败 id=%s error=%s", cur_id, msg)
            return final
        self.logger_.info("ProcessAgent 任务领取成功 id=%s", cur_id)

        try:
            context = self.build_context(objective=objective, plan_items=items, current_item=item)
            result_text = self._run_llm_until_final(context)
            self.logger_.info("ProcessAgent 任务执行完成 id=%s result_len=%d", cur_id, len(result_text))
            self._append_response_and_complete(item, result_text, plan_id)
        finally:
            self._invoke_todo({"op": "release", "id": cur_id, "by": self.name_})
            self.logger_.info("ProcessAgent 已释放任务 id=%s", cur_id)

        final = f"已完成任务#{cur_id}：{item.get('content')}\n结果：{result_text}"
        self.append_history(Message(role="assistant", action="final", content=final))
        self.logger_.info("ProcessAgent 结束：任务#%s已完成", cur_id)
        return final