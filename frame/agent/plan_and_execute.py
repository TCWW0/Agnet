"""PlanAndExecuteAgent：MVP 版的 plan-and-execute 执行器。

核心思路：
1) 先规划：让 LLM 生成任务清单，并写入 TODOTool。
2) 再执行：逐条 claim -> 执行 -> add_response -> update(COMPLETED) -> release。
3) 通过 ExecutionContext 传递全局目标、计划摘要和最近执行结果，减少上下文丢失与重复回答。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from frame.core.base_agent import BaseAgent, AgentConfig
from frame.core.config import LLMConfig
from frame.core.llm import LLMClient
from frame.core.logger import Logger, Level
from frame.core.message import Message, ToolMessage, ToolResult
from frame.tool.registry import ToolRegistry
from frame.tool.todo import TODOTool


PLAN_PROMPT_TEMPLATE = """你是任务规划器。请把用户目标拆成 2-6 条可执行子任务。
要求：
1. 仅输出 JSON 数组，不要输出其它文本。
2. 数组元素可以是字符串，或对象（对象应包含 content 字段）。
3. 子任务要短小、明确、避免重复。

用户目标：
{objective}
"""


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
1. 仅输出一行：final <执行结果>。
2. 执行结果应尽量具体，且不要与最近结果机械重复。
"""


@dataclass
class ExecutedItem:
	item_id: int
	content: str
	response: str
	status: str = "COMPLETED"
	duplicate_of: Optional[int] = None
	timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class ExecutionContext:
	objective: str
	plan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
	created_at: str = field(default_factory=lambda: datetime.now().isoformat())
	plan_items: List[Dict[str, Any]] = field(default_factory=list)
	executed_items: List[ExecutedItem] = field(default_factory=list)
	task_fingerprints: Dict[str, int] = field(default_factory=dict)
	response_fingerprints: Dict[str, int] = field(default_factory=dict)

	def plan_summary(self, max_items: int = 8) -> str:
		if not self.plan_items:
			return "(空计划)"
		lines: List[str] = []
		for item in self.plan_items[:max_items]:
			item_id = item.get("id")
			content = item.get("content")
			lines.append(f"- #{item_id} {content}")
		if len(self.plan_items) > max_items:
			lines.append(f"- ... 其余 {len(self.plan_items) - max_items} 项")
		return "\n".join(lines)

	def recent_results_summary(self, max_items: int = 3) -> str:
		if not self.executed_items:
			return "(暂无)"
		rows: List[str] = []
		for one in self.executed_items[-max_items:]:
			snippet = one.response.replace("\n", " ").strip()
			if len(snippet) > 90:
				snippet = snippet[:87] + "..."
			rows.append(f"- #{one.item_id} {one.content}: {snippet}")
		return "\n".join(rows)


class PlanAndExecuteAgent(BaseAgent):
	"""MVP 版 plan-and-execute Agent。

	- 规划阶段：从 LLM 提取任务列表并写入 TODOTool。
	- 执行阶段：逐项执行并把结果回写到对应 TODO item。
	- 去重策略：
	  1) 计划去重：相同任务内容只保留一条。
	  2) 响应去重：若不同任务得到相同回答，为后续任务标记“重复”。
	"""

	def __init__(
		self,
		name: str,
		config: AgentConfig,
		llm: LLMClient,
		logger: Optional[Logger] = None,
		workflow_id: str = "plan_and_execute_workflow",
		todo_storage_path: str = "todo_state.json",
	):
		m_logger = logger or Logger(file_name=f"{name}.log", min_level=Level.DEBUG)
		super().__init__(name, config, llm, workflow_id=workflow_id, logger=m_logger)

		self.tool_registry = ToolRegistry()
		self.tool_registry.register(TODOTool(storage_path=todo_storage_path))
		self.last_context: Optional[ExecutionContext] = None
		self.build()

	def init_sys_prompt(self) -> str:
		return (
			"你是 PlanAndExecuteAgent，负责先规划再执行。\n"
			"规则：始终用中文；优先保证执行可追踪（claim/add_response/update/release）。\n"
			"输出给用户时要包含总数、完成数和每个任务的简要结果。"
		)

	@staticmethod
	def _normalize_text(text: str) -> str:
		compact = " ".join(str(text).strip().split())
		return compact.lower()

	@classmethod
	def _fingerprint(cls, text: str) -> str:
		normalized = cls._normalize_text(text)
		return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

	@staticmethod
	def _extract_task_from_obj(obj: Any) -> Optional[str]:
		if isinstance(obj, str):
			t = obj.strip()
			return t if t else None
		if isinstance(obj, dict):
			for key in ("content", "task", "title", "step", "todo"):
				val = obj.get(key)
				if isinstance(val, str) and val.strip():
					return val.strip()
		return None

	@staticmethod
	def _strip_list_prefix(line: str) -> str:
		return re.sub(r"^[\s\-\*\d\)\(\.、]+", "", line).strip()

	def _invoke_todo(self, tool_input: Any) -> ToolResult:
		call_msg = ToolMessage(tool_name="TODO", tool_input=tool_input, phase="call")
		return self.tool_registry.invoke("TODO", call_msg)

	def _list_all_items(self) -> List[Dict[str, Any]]:
		tr = self._invoke_todo({"op": "list"})
		if tr.status != "ok" or not isinstance(tr.output, list):
			return []
		return [it for it in tr.output if isinstance(it, dict)]

	def _list_plan_items(self, plan_id: str) -> List[Dict[str, Any]]:
		all_items = self._list_all_items()
		selected: List[Dict[str, Any]] = []
		for it in all_items:
			meta = it.get("metadata")
			if isinstance(meta, dict) and meta.get("plan_id") == plan_id:
				selected.append(it)
		selected.sort(key=lambda x: int(x.get("id", 0)))
		return selected

	def _extract_plan_tasks(self, raw: str, objective: str) -> List[str]:
		tasks: List[str] = []

		parsed: Any = None
		try:
			parsed = json.loads(raw)
		except Exception:
			parsed = None

		if isinstance(parsed, list):
			for one in parsed:
				t = self._extract_task_from_obj(one)
				if t:
					tasks.append(t)
		elif isinstance(parsed, dict):
			for key in ("tasks", "plan", "items", "todo"):
				val = parsed.get(key)
				if isinstance(val, list):
					for one in val:
						t = self._extract_task_from_obj(one)
						if t:
							tasks.append(t)
					break

		if not tasks:
			msgs = Message.convert_many_from_str(raw)
			for m in msgs:
				content = str(getattr(m, "content", "") or "").strip()
				if not content:
					continue
				for line in content.splitlines():
					line2 = self._strip_list_prefix(line)
					if line2:
						tasks.append(line2)

		unique_tasks: List[str] = []
		seen: set[str] = set()
		for t in tasks:
			fp = self._fingerprint(t)
			if fp in seen:
				continue
			seen.add(fp)
			unique_tasks.append(t)
			if len(unique_tasks) >= 6:
				break

		if not unique_tasks:
			unique_tasks = [f"完成用户请求：{objective}"]
		return unique_tasks

	def _plan_with_llm(self, ctx: ExecutionContext) -> List[str]:
		prompt = PLAN_PROMPT_TEMPLATE.format(objective=ctx.objective)
		try:
			raw = self.llm_.invoke(prompt)
		except Exception as e:
			self.logger_.warning("规划阶段调用 LLM 失败，使用回退计划: %s", str(e))
			return [f"完成用户请求：{ctx.objective}"]

		tasks = self._extract_plan_tasks(raw or "", ctx.objective)
		self.append_history(Message(role="assistant", action="think", content=f"规划阶段生成 {len(tasks)} 条待办"))
		return tasks

	def _persist_plan(self, ctx: ExecutionContext, tasks: List[str]) -> None:
		ops: List[Dict[str, Any]] = []
		for idx, task in enumerate(tasks, start=1):
			ops.append(
				{
					"op": "add",
					"content": task,
					"metadata": {
						"source": "plan_and_execute",
						"plan_id": ctx.plan_id,
						"objective": ctx.objective,
						"order": idx,
					},
				}
			)

		payload: Any = {"ops": ops} if len(ops) > 1 else ops[0]
		tr = self._invoke_todo(payload)
		if tr.status != "ok":
			self.logger_.warning("写入计划到 TODO 出现错误: %s", tr.error_message or tr.nl)

		plan_items = self._list_plan_items(ctx.plan_id)
		if not plan_items:
			self.logger_.warning("计划落库后未查询到任务，执行回退写入")
			self._invoke_todo(
				{
					"op": "add",
					"content": f"完成用户请求：{ctx.objective}",
					"metadata": {
						"source": "plan_and_execute",
						"plan_id": ctx.plan_id,
						"objective": ctx.objective,
						"order": 1,
					},
				}
			)
			plan_items = self._list_plan_items(ctx.plan_id)

		ctx.plan_items = plan_items

	def _extract_execute_final(self, raw: str) -> str:
		text = (raw or "").strip()
		if not text:
			return "执行完成，但模型未返回内容。"

		msgs = Message.convert_many_from_str(text)
		for m in msgs:
			if getattr(m, "action", None) == "final":
				content = str(getattr(m, "content", "") or "").strip()
				if content:
					return content

		for m in msgs:
			content = str(getattr(m, "content", "") or "").strip()
			if content:
				return content

		return text

	def _execute_with_llm(self, ctx: ExecutionContext, item_id: int, item_content: str) -> str:
		prompt = EXECUTE_PROMPT_TEMPLATE.format(
			objective=ctx.objective,
			plan_summary=ctx.plan_summary(),
			recent_results=ctx.recent_results_summary(),
			item_id=item_id,
			item_content=item_content,
		)
		try:
			raw = self.llm_.invoke(prompt)
		except Exception as e:
			return f"执行失败：{str(e)}"
		return self._extract_execute_final(raw)

	def _execute_plan(self, ctx: ExecutionContext) -> None:
		# 初始化任务 fingerprint 索引，避免同计划下重复执行
		for one in ctx.plan_items:
			content = str(one.get("content", "") or "").strip()
			item_id = int(one.get("id", 0) or 0)
			if content and item_id > 0:
				fp = self._fingerprint(content)
				if fp not in ctx.task_fingerprints:
					ctx.task_fingerprints[fp] = item_id

		for one in ctx.plan_items:
			item_id = int(one.get("id", 0) or 0)
			content = str(one.get("content", "") or "").strip()
			if item_id <= 0 or not content:
				continue

			status = str(one.get("status", "") or "").upper()
			if status == "COMPLETED":
				continue

			content_fp = self._fingerprint(content)
			first_item_id = ctx.task_fingerprints.get(content_fp)
			if first_item_id is not None and first_item_id != item_id:
				note = f"与任务#{first_item_id} 内容重复，已跳过执行。"
				self._invoke_todo(
					{
						"op": "add_response",
						"id": item_id,
						"response": note,
						"by": self.name_,
						"metadata": {
							"plan_id": ctx.plan_id,
							"duplicate_of": first_item_id,
						},
					}
				)
				self._invoke_todo(
					{
						"op": "update",
						"id": item_id,
						"status": "CANCELLED",
						"metadata": {
							"plan_id": ctx.plan_id,
							"duplicate_of": first_item_id,
						},
					}
				)
				ctx.executed_items.append(
					ExecutedItem(
						item_id=item_id,
						content=content,
						response=note,
						status="CANCELLED",
						duplicate_of=first_item_id,
					)
				)
				continue

			claim_tr = self._invoke_todo({"op": "claim", "id": item_id, "by": self.name_})
			if claim_tr.status != "ok":
				err_msg = claim_tr.error_message or claim_tr.nl or "claim failed"
				self.logger_.warning("任务 %s claim 失败: %s", item_id, err_msg)
				ctx.executed_items.append(
					ExecutedItem(item_id=item_id, content=content, response=f"claim失败：{err_msg}", status="SKIPPED")
				)
				continue

			try:
				response = self._execute_with_llm(ctx, item_id, content)
				resp_fp = self._fingerprint(response)
				duplicate_of = ctx.response_fingerprints.get(resp_fp)
				if duplicate_of is not None and duplicate_of != item_id:
					response = f"与任务#{duplicate_of} 的执行结果重复，保留同结论。{response}"
				else:
					ctx.response_fingerprints[resp_fp] = item_id

				self._invoke_todo(
					{
						"op": "add_response",
						"id": item_id,
						"response": response,
						"by": self.name_,
						"metadata": {
							"plan_id": ctx.plan_id,
							"response_fingerprint": resp_fp,
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
							"plan_id": ctx.plan_id,
							"executed_by": self.name_,
							"response_fingerprint": resp_fp,
							"duplicate_of": duplicate_of,
						},
					}
				)

				ctx.executed_items.append(
					ExecutedItem(
						item_id=item_id,
						content=content,
						response=response,
						status="COMPLETED",
						duplicate_of=duplicate_of,
					)
				)
			finally:
				self._invoke_todo({"op": "release", "id": item_id, "by": self.name_})

	def _build_final_text(self, ctx: ExecutionContext) -> str:
		total = len(ctx.plan_items)
		completed = sum(1 for x in ctx.executed_items if x.status == "COMPLETED")
		cancelled = sum(1 for x in ctx.executed_items if x.status == "CANCELLED")
		skipped = sum(1 for x in ctx.executed_items if x.status == "SKIPPED")

		lines = [
			f"plan_id={ctx.plan_id}，共 {total} 项，完成 {completed} 项，取消 {cancelled} 项，跳过 {skipped} 项。"
		]
		for one in ctx.executed_items:
			snippet = one.response.replace("\n", " ").strip()
			if len(snippet) > 90:
				snippet = snippet[:87] + "..."
			lines.append(f"#{one.item_id} [{one.status}] {one.content} -> {snippet}")
		return "\n".join(lines)

	def _think_impl(self, input: str) -> str:
		user_msg = Message(role="user", action="input", content=input)
		self.append_history(user_msg)

		ctx = ExecutionContext(objective=input)
		self.last_context = ctx

		plan_tasks = self._plan_with_llm(ctx)
		self._persist_plan(ctx, plan_tasks)
		self._execute_plan(ctx)

		final_text = self._build_final_text(ctx)
		final_msg = Message(role="assistant", action="final", content=final_text)
		self.append_history(final_msg)
		return final_text


if __name__ == "__main__":
	agent_config = AgentConfig.from_env()
	llm_config = LLMConfig.from_env()
	llm_client = LLMClient(llm_config)
	agent = PlanAndExecuteAgent("DemoPlanExecuteAgent", agent_config, llm_client)

	print("PlanAndExecuteAgent ready. 输入 'exit' 或 'quit' 退出。")
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
				answer = agent.think(user)
			except Exception as e:
				agent.logger_.error("PlanAndExecuteAgent 调用失败: %s", str(e))
				answer = "[agent error]"
			print("Agent回答：", answer)
	except KeyboardInterrupt:
		print("\n退出")

