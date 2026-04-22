from __future__ import annotations

from pathlib import Path
from typing import Iterator, Sequence

from src.schemas import ChatMessage

from .orchestrator import SkillRagOrchestrator
from .registry import SkillRegistry
from .router import DeterministicSkillRouter
from .skills import MapSkill, PathRetrieveSkill, VectorRetrieveSkill


class SkillRagChatEngine:
    """Hybrid Skill-RAG engine with deterministic routing and trace output."""

    def __init__(
        self,
        knowledge_base_root: Path,
        knowledge_chunks_root: Path,
        knowledge_summary_root: Path,
        top_k: int = 4,
        max_skill_calls: int = 3,
    ) -> None:
        registry = SkillRegistry()
        registry.register(MapSkill(summary_root=knowledge_summary_root, default_top_k=top_k))
        registry.register(PathRetrieveSkill(knowledge_base_root=knowledge_base_root))
        registry.register(VectorRetrieveSkill(chunks_root=knowledge_chunks_root, default_top_k=top_k))

        self._orchestrator = SkillRagOrchestrator(
            registry=registry,
            router=DeterministicSkillRouter(),
            max_skill_calls=max_skill_calls,
            top_k=top_k,
        )
        self._last_trace: list[dict[str, object]] = []

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        latest_user = ""
        for msg in reversed(messages):
            if msg.role == "user":
                latest_user = msg.content
                break

        if not latest_user.strip():
            self._last_trace = []
            return "No user input was detected for Skill-RAG retrieval."

        history = [{"role": msg.role, "content": msg.content} for msg in messages]
        result = self._orchestrator.run(query=latest_user, history=history)
        self._last_trace = [trace.model_dump(mode="json") for trace in result.traces]
        return result.answer

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        text = self.generate(messages)
        chunk_size = 24
        if not text:
            yield ""
            return

        for idx in range(0, len(text), chunk_size):
            yield text[idx : idx + chunk_size]

    def get_last_trace(self) -> list[dict[str, object]]:
        return list(self._last_trace)
