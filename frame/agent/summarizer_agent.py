"""SummarizerAgent：汇总已执行 TODO 项并生成面向用户目标的总结。"""

import json
from typing import Any, Dict, List, Optional

from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.logger import Logger, Level
from frame.core.message import Message, ToolMessage, ToolResult
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool


SUMMARY_SYS_PROMPT = (
    "你是 SummarizerAgent，负责基于已执行任务产出简洁且有条理的中文总结。\n"
    "你不能调用工具，输出仅允许一条 final。\n"
    "总结必须围绕用户原始目标，包含进度与关键结论。"
)

SUMMARY_PROMPT_TEMPLATE = """请根据以下信息给出最终总结：

原始目标：
{objective}

进度统计：
{progress}

任务概览：
{plan_summary}

关键执行结果（已去重）：
{completed_results}

未完成项：
{pending_items}

输出要求：
1. 仅输出一行：final <总结文本>。
2. 紧扣“原始目标”，先给结论，再给进展和下一步建议。
3. 不要捏造未出现的信息。
"""


class SummarizerAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        config: AgentConfig,
        llm: LLMClient,
        workflow_id: str,
        logger: Optional[Logger] = None,
        todo_tool: Optional[TODOTool] = None,
        plan_summary_limit: int = 20,
        pending_summary_limit: int = 5,
    ):
        m_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
        assert todo_tool is not None, "SummarizerAgent requires a TODOTool instance"

        self.todo_tool_ = todo_tool
        self.plan_summary_limit_ = max(1, int(plan_summary_limit))
        self.pending_summary_limit_ = max(1, int(pending_summary_limit))

        super().__init__(name, config, llm, workflow_id=workflow_id, logger=m_logger)

        self.tool_registry_ = ToolRegistry()
        self.tool_registry_.register(todo_tool)
        self.build()

    def init_sys_prompt(self) -> str:
        return SUMMARY_SYS_PROMPT

    def _invoke_todo(self, tool_input: Dict[str, Any]) -> ToolResult:
        msg = ToolMessage(tool_name="TODO", tool_input=tool_input, phase="call")
        return self.tool_registry_.invoke("TODO", msg)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(str(text).strip().split()).lower()

    @staticmethod
    def _parse_request(input_text: str) -> Dict[str, Optional[str]]:
        req: Dict[str, Optional[str]] = {
            "objective": None,
            "plan_id": None,
            "mode": "full",
        }
        if not isinstance(input_text, str):
            return req

        text = input_text.strip()
        if not text:
            return req

        try:
            obj = json.loads(text)
        except Exception:
            req["objective"] = text
            return req

        if not isinstance(obj, dict):
            req["objective"] = text
            return req

        objective = obj.get("objective") or obj.get("query") or obj.get("input")
        if isinstance(objective, str) and objective.strip():
            req["objective"] = objective.strip()

        plan_id = obj.get("plan_id")
        if isinstance(plan_id, str) and plan_id.strip():
            req["plan_id"] = plan_id.strip()

        mode = obj.get("mode")
        if isinstance(mode, str) and mode.strip():
            req["mode"] = mode.strip().lower()
        return req

    @staticmethod
    def _get_item_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
        meta = item.get("metadata")
        return meta if isinstance(meta, dict) else {}

    def _match_workflow(self, item: Dict[str, Any]) -> bool:
        meta = self._get_item_metadata(item)
        if str(meta.get("workflow_id") or "") == self.workflow_id_:
            return True

        responses = item.get("responses")
        if not isinstance(responses, list):
            return False
        for one in responses:
            if not isinstance(one, dict):
                continue
            r_meta = one.get("metadata") if isinstance(one.get("metadata"), dict) else {}
            if str(r_meta.get("workflow_id") or "") == self.workflow_id_: # type: ignore
                return True
        return False

    def _list_target_items(self, plan_id: Optional[str]) -> List[Dict[str, Any]]:
        tr = self._invoke_todo({"op": "list"})
        if tr.status != "ok" or not isinstance(tr.output, list):
            return []

        all_items = [it for it in tr.output if isinstance(it, dict)]
        all_items.sort(key=lambda x: int(x.get("id", 0) or 0))

        if plan_id:
            by_plan: List[Dict[str, Any]] = []
            for it in all_items:
                meta = self._get_item_metadata(it)
                if str(meta.get("plan_id") or "") == plan_id:
                    by_plan.append(it)
            if by_plan:
                self.logger_.info("SummarizerAgent 按 plan_id=%s 命中任务 %d 条", plan_id, len(by_plan))
                return by_plan

        by_workflow = [it for it in all_items if self._match_workflow(it)]
        self.logger_.info("SummarizerAgent 按 workflow_id=%s 命中任务 %d 条", self.workflow_id_, len(by_workflow))
        return by_workflow

    @staticmethod
    def _latest_response_text(item: Dict[str, Any]) -> str:
        responses = item.get("responses")
        if not isinstance(responses, list) or not responses:
            return ""
        for one in reversed(responses):
            if not isinstance(one, dict):
                continue
            text = str(one.get("content") or "").strip()
            if text:
                return text
        return ""

    # 尝试获取原始的问题，俩条路径：一是直接查看外部是否传来了objective字段，二是查看每个Item的metadata里是否有objective字段，找到第一个非空的作为原始目标
    def _resolve_objective(self, objective: Optional[str], items: List[Dict[str, Any]]) -> str:
        if isinstance(objective, str) and objective.strip():
            return objective.strip()
        for it in items:
            meta = self._get_item_metadata(it)
            text = str(meta.get("objective") or "").strip()
            if text:
                return text
        return "(未提供原始目标)"

    # 收集当前属于本工作流的所有任务，构建上下文信息，包含总体目标、计划摘要、已完成结果、待处理任务等，为后续的总结提供信息支持
    def build_context(self, objective: str, items: List[Dict[str, Any]], mode: str = "full") -> Dict[str, str]:
        total = len(items)
        completed_items: List[Dict[str, Any]] = []
        in_progress_items: List[Dict[str, Any]] = []
        pending_items: List[Dict[str, Any]] = []
        cancelled_items: List[Dict[str, Any]] = []

        for it in items:
            status = str(it.get("status") or "").upper()
            if status == "COMPLETED":
                completed_items.append(it)
            elif status == "IN_PROGRESS":
                in_progress_items.append(it)
            elif status == "CANCELLED":
                cancelled_items.append(it)
            else:
                pending_items.append(it)

        progress = (
            f"总任务 {total} 项；"
            f"已完成 {len(completed_items)} 项；"
            f"进行中 {len(in_progress_items)} 项；"
            f"待处理 {len(pending_items)} 项；"
            f"已取消 {len(cancelled_items)} 项。"
        )

        plan_rows: List[str] = []
        for it in items[: self.plan_summary_limit_]:
            item_id = int(it.get("id", 0) or 0)
            status = str(it.get("status") or "")
            content = str(it.get("content") or "")
            plan_rows.append(f"- #{item_id} [{status}] {content}")
        if len(items) > self.plan_summary_limit_:
            plan_rows.append(f"- ... 其余 {len(items) - self.plan_summary_limit_} 项")
        if not plan_rows:
            plan_rows = ["(空)"]

        # 关键结果去重：优先看 duplicate_of，其次看文本归一化
        completed_rows: List[str] = []
        seen_norm: set[str] = set()
        dedup_count = 0
        for it in completed_items:
            item_id = int(it.get("id", 0) or 0)
            content = str(it.get("content") or "")
            meta = self._get_item_metadata(it)
            duplicate_of = meta.get("duplicate_of")
            result = self._latest_response_text(it)
            if not result:
                continue

            norm = self._normalize_text(result)
            if duplicate_of or (norm and norm in seen_norm):
                dedup_count += 1
                continue
            if norm:
                seen_norm.add(norm)

            snippet = result.replace("\n", " ")
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            completed_rows.append(f"- #{item_id} {content}: {snippet}")

        if mode == "incremental" and completed_rows:
            completed_rows = completed_rows[-self.pending_summary_limit_ :]

        if not completed_rows:
            completed_rows = ["(暂无可汇总结果)"]

        pending_rows: List[str] = []
        for it in (pending_items + in_progress_items)[: self.pending_summary_limit_]:
            item_id = int(it.get("id", 0) or 0)
            status = str(it.get("status") or "")
            content = str(it.get("content") or "")
            pending_rows.append(f"- #{item_id} [{status}] {content}")
        if not pending_rows:
            pending_rows = ["(无)"]

        return {
            "objective": objective,
            "progress": progress,
            "plan_summary": "\n".join(plan_rows),
            "completed_results": "\n".join(completed_rows),
            "pending_items": "\n".join(pending_rows),
            "dedup_count": str(dedup_count),
        }

    def _fallback_summary(self, context: Dict[str, str]) -> str:
        objective = context.get("objective") or "(未提供原始目标)"
        progress = context.get("progress") or ""
        completed = context.get("completed_results") or ""
        pending = context.get("pending_items") or ""

        if "暂无可汇总结果" in completed:
            return f"围绕目标“{objective}”，当前进展：{progress} 暂无可总结的执行结果。建议优先推进以下任务：{pending}"

        return (
            f"围绕目标“{objective}”，当前进展：{progress} "
            f"关键结论：{completed} 下一步建议：{pending}"
        )

    def _summarize_with_llm(self, context: Dict[str, str]) -> str:
        prompt = SUMMARY_PROMPT_TEMPLATE.format(
            objective=context["objective"],
            progress=context["progress"],
            plan_summary=context["plan_summary"],
            completed_results=context["completed_results"],
            pending_items=context["pending_items"],
        )

        try:
            raw = self.llm_.invoke(prompt)
        except Exception as e:
            self.logger_.warning("SummarizerAgent 调用 LLM 失败，回退模板总结: %s", str(e))
            return self._fallback_summary(context)

        msgs = Message.convert_many_from_str(raw)
        for m in msgs:
            if getattr(m, "action", None) == "final":
                text = str(getattr(m, "content", "") or "").strip()
                if text:
                    return text

        # 兼容模型没按 action 输出的场景
        text = str(raw or "").strip()
        if text:
            return text
        return self._fallback_summary(context)

    def _think_impl(self, input: str) -> str:
        self.append_history(Message(role="user", action="input", content=input))

        req = self._parse_request(input)
        plan_id = req.get("plan_id")
        mode = str(req.get("mode") or "full").lower()
        self.logger_.info("SummarizerAgent 开始汇总，workflow_id=%s，plan_id=%s，mode=%s", self.workflow_id_, plan_id, mode)

        items = self._list_target_items(plan_id)
        if not items:
            final = f"未找到属于 workflow_id={self.workflow_id_} 的可汇总任务。"
            self.append_history(Message(role="assistant", action="final", content=final))
            self.logger_.info("SummarizerAgent 结束：无可汇总任务")
            return final

        objective = self._resolve_objective(req.get("objective"), items)
        context = self.build_context(objective=objective, items=items, mode=mode)
        self.logger_.info("SummarizerAgent 上下文就绪：%s", context.get("progress"))
        summary = self._summarize_with_llm(context)

        # 轻量附加进度与去重统计，保证输出可解释
        final = (
            f"{summary}\n"
            f"进度：{context['progress']}\n"
            f"去重折叠：{context['dedup_count']} 条"
        )

        # 将最终输出结果添加到TODOTool的历史中，便于后续查询和复盘，同时也保证了输出结果的可追溯性
        payload = {
            "op": "add",
            "content": f"总结：{summary}",
            "metadata": {
                "type": "summary",
                "workflow_id": self.workflow_id_,
                "plan_id": plan_id,
                "objective": objective,
                "progress": context.get("progress"),
                "by": "SummarizerAgent",
            },  
        }
        tr = self._invoke_todo(payload)
        if tr.status != "ok":
            self.logger_.warning("SummarizerAgent 无法将总结添加到 TODO 中，工具调用失败: %s", tr.output)
        self.append_history(Message(role="assistant", action="final", content=final))
        self.logger_.info("SummarizerAgent 汇总完成，去重折叠=%s", context.get("dedup_count"))
        return final
