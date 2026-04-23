from __future__ import annotations

from threading import RLock
from typing import Dict, List, Literal, Optional, Protocol, Sequence, cast

from pydantic import BaseModel, Field

from frame.core.message import Message
from frame.tool.base import BaseTool, Property, ToolDesc, ToolParameters, ToolResponse, ValidationResult

MemoryScope = Literal["all", "recent", "facts"]


class SessionRef(BaseModel):
	session_id: str = Field(min_length=1)
	agent_id: Optional[str] = None


class MemoryPolicy(BaseModel):
	max_history_items: int = Field(default=80, ge=1)
	retrieval_top_k: int = Field(default=5, ge=1)
	enable_retrieval: bool = True

# 支持下面所有约定的方法都可作为一个Kernal
class MemoryKernel(Protocol):
	def load_recent(self, session: SessionRef, limit: int) -> List[Message]:
		...

	def query(self, session: SessionRef, text: str, top_k: int) -> List[Message]:
		...

	def append(self, session: SessionRef, messages: Sequence[Message]) -> None:
		...

	def clear(self, session: SessionRef, scope: MemoryScope = "all") -> None:
		...


class InMemoryMemoryKernel:
	"""MVP in-memory kernel used by both forced hooks and tool facade."""

	def __init__(self) -> None:
		self._recent_store: Dict[str, List[Message]] = {}
		self._fact_store: Dict[str, List[Message]] = {}
		self._lock = RLock()

    # 简单的获取最近K条消息，按时间顺序返回（从旧到新）
	def load_recent(self, session: SessionRef, limit: int) -> List[Message]:
		safe_limit = max(0, limit)
		with self._lock:
			items = self._recent_store.get(session.session_id, [])
			if safe_limit == 0:
				return []
			return [msg.model_copy(deep=True) for msg in items[-safe_limit:]]

	def query(self, session: SessionRef, text: str, top_k: int) -> List[Message]:
		safe_top_k = max(1, top_k)
		normalized = text.strip().lower()

		with self._lock:
			facts = self._fact_store.get(session.session_id, [])
			recent = self._recent_store.get(session.session_id, [])
			merged = facts + recent

			if not merged:
				return []

			if not normalized:
				return [msg.model_copy(deep=True) for msg in merged[-safe_top_k:]]

			scored = []
			for index, msg in enumerate(merged):
				score = self._score_text(normalized, msg.content)
				if score > 0:
					scored.append((score, index, msg))

			if not scored:
				return [msg.model_copy(deep=True) for msg in merged[-safe_top_k:]]

			scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
			selected = [item[2] for item in scored[:safe_top_k]]
			return [msg.model_copy(deep=True) for msg in selected]

	def append(self, session: SessionRef, messages: Sequence[Message]) -> None:
		if not messages:
			return
		with self._lock:
			bucket = self._recent_store.setdefault(session.session_id, [])
			bucket.extend(msg.model_copy(deep=True) for msg in messages)

	def clear(self, session: SessionRef, scope: MemoryScope = "all") -> None:
		with self._lock:
			if scope in {"all", "recent"}:
				self._recent_store.pop(session.session_id, None)
			if scope in {"all", "facts"}:
				self._fact_store.pop(session.session_id, None)

	def remember_fact(self, session: SessionRef, text: str) -> None:
		fact = Message(role="system", content=text)
		with self._lock:
			facts = self._fact_store.setdefault(session.session_id, [])
			facts.append(fact)

    # 简单的关键字匹配打分，完全匹配得分最高，部分匹配按包含的token数量打分
	@staticmethod
	def _score_text(query_text: str, candidate_text: str) -> int:
		candidate_normalized = candidate_text.lower()
		if query_text in candidate_normalized:
			return 100

		query_tokens = [token for token in query_text.split() if token]
		if not query_tokens:
			return 0

		score = 0
		for token in query_tokens:
			if token in candidate_normalized:
				score += 1
		return score


class AgentMemoryHooks:
	"""Forced memory path, executed before and after each agent round."""

	def __init__(self, kernel: MemoryKernel, policy: Optional[MemoryPolicy] = None) -> None:
		self.kernel = kernel
		self.policy = policy or MemoryPolicy()

	def before_invoke(
		self,
		session: SessionRef,
		user_input: str,
		base_messages: Sequence[Message],
	) -> List[Message]:
		recent = self.kernel.load_recent(session, self.policy.max_history_items)
		merged: List[Message] = []
		merged.extend(recent)

		if self.policy.enable_retrieval:
			recalled = self.kernel.query(session, user_input, self.policy.retrieval_top_k)
			merged.extend(recalled)

		merged.extend(base_messages)
		return self._dedupe_messages(merged)

	def after_invoke(self, session: SessionRef, new_messages: Sequence[Message]) -> None:
		if not new_messages:
			return
		self.kernel.append(session, new_messages)

	@staticmethod
	def _dedupe_messages(messages: Sequence[Message]) -> List[Message]:
		seen = set()
		output: List[Message] = []
		for msg in messages:
			key = (msg.role, msg.type, msg.time_str, msg.content)
			if key in seen:
				continue
			seen.add(key)
			output.append(msg)
		return output


class MemoryToolFacade:
	"""Tool-friendly memory facade; reads and writes still go through the same kernel."""

	def __init__(self, kernel: MemoryKernel) -> None:
		self.kernel = kernel

	def remember(self, session: SessionRef, text: str) -> str:
		cleaned = text.strip()
		if not cleaned:
			return "empty memory ignored"

		if hasattr(self.kernel, "remember_fact"):
			remember_fact = getattr(self.kernel, "remember_fact")
			remember_fact(session, cleaned)
		else:
			self.kernel.append(session, [Message(role="system", content=cleaned)])
		return "ok"

	def recall(self, session: SessionRef, query: str, top_k: int = 3) -> List[str]:
		messages = self.kernel.query(session, query, max(1, top_k))
		return [msg.content for msg in messages]

	def forget(self, session: SessionRef, scope: MemoryScope = "all") -> str:
		self.kernel.clear(session, scope)
		return "ok"


class MemoryRecallTool(BaseTool):
	def __init__(self, facade: MemoryToolFacade, session: SessionRef):
		super().__init__(name="memory_recall", description="Recall memory snippets by query text")
		self.facade_ = facade
		self.session_ = session

	@classmethod
	def desc(cls) -> ToolDesc:
		params = ToolParameters(
			properties={
				"query": Property(type="string", description="Text query for memory retrieval"),
				"top_k": Property(type="integer", description="Maximum number of matched memories"),
			},
			required=["query"],
		)
		return ToolDesc(name="memory_recall", description="Recall related memories", parameters=params)

	def valid_paras(self, params: Dict[str, str]) -> "ValidationResult":
		query = params.get("query")
		if not isinstance(query, str) or not query.strip():
			return ValidationResult(valid=False, message="missing or empty 'query' parameter")
		# top_k 尝试解析为整数，若失败使用默认 3
		top_k_raw = params.get("top_k", 3)
		try:
			top_k = int(str(top_k_raw))
			if top_k < 1:
				top_k = 3
		except Exception:
			top_k = 3
		return ValidationResult(valid=True, parsed_params={"query": query, "top_k": top_k})

	def _execute_impl(self, params: Dict[str, str]) -> ToolResponse:
		query = params.get("query", "")
		top_k_raw = params.get("top_k", "3")
		try:
			top_k = int(str(top_k_raw))
		except (TypeError, ValueError):
			top_k = 3

		memories = self.facade_.recall(self.session_, query=query, top_k=max(1, top_k))
		if not memories:
			output = "no matched memory"
		else:
			output = "\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(memories))
		return ToolResponse(tool_name=self.name, status="success", output=output)


class MemoryRememberTool(BaseTool):
	def __init__(self, facade: MemoryToolFacade, session: SessionRef):
		super().__init__(name="memory_remember", description="Persist one memory statement")
		self.facade_ = facade
		self.session_ = session

	@classmethod
	def desc(cls) -> ToolDesc:
		params = ToolParameters(
			properties={
				"text": Property(type="string", description="Memory text to store"),
			},
			required=["text"],
		)
		return ToolDesc(name="memory_remember", description="Store one memory", parameters=params)

	def valid_paras(self, params: Dict[str, str]) -> "ValidationResult":
		text = params.get("text")
		if not isinstance(text, str) or not text.strip():
			return ValidationResult(valid=False, message="missing or empty 'text' parameter")
		return ValidationResult(valid=True, parsed_params={"text": text.strip()})

	def _execute_impl(self, params: Dict[str, str]) -> ToolResponse:
		text = params.get("text", "")
		output = self.facade_.remember(self.session_, text)
		return ToolResponse(tool_name=self.name, status="success", output=output)


class MemoryForgetTool(BaseTool):
	def __init__(self, facade: MemoryToolFacade, session: SessionRef):
		super().__init__(name="memory_forget", description="Clear memory in specific scope")
		self.facade_ = facade
		self.session_ = session

	@classmethod
	def desc(cls) -> ToolDesc:
		params = ToolParameters(
			properties={
				"scope": Property(type="string", description="all | recent | facts", enum=["all", "recent", "facts"]),
			},
			required=["scope"],
		)
		return ToolDesc(name="memory_forget", description="Clear memory by scope", parameters=params)

	def valid_paras(self, params: Dict[str, str]) -> "ValidationResult":
		scope = params.get("scope")
		if scope not in {"all", "recent", "facts"}:
			return ValidationResult(valid=False, message=f"invalid scope '{scope}', expected one of all|recent|facts")
		return ValidationResult(valid=True, parsed_params={"scope": scope})

	def _execute_impl(self, params: Dict[str, str]) -> ToolResponse:
		scope_raw = params.get("scope", "all")
		scope = cast(MemoryScope, scope_raw)
		output = self.facade_.forget(self.session_, scope=scope)
		return ToolResponse(tool_name=self.name, status="success", output=output)


def build_memory_tools(facade: MemoryToolFacade, session: SessionRef) -> List[BaseTool]:
	return [
		MemoryRecallTool(facade=facade, session=session),
		MemoryRememberTool(facade=facade, session=session),
		MemoryForgetTool(facade=facade, session=session),
	]

