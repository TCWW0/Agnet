from __future__ import annotations

from uuid import uuid4
from typing import Iterator

from src.config import AppConfig
from src.engines import ChatEngine, FrameChatEngine, MockChatEngine, SimpleOpenAIEngine
from src.skill_rag.engine import SkillRagChatEngine
from src.schemas import AssistantMessage, ChatRequest
from src.stream_framing import StreamFrame, StreamFramer


class ChatService:
    """Application service for chat reply and chunk streaming."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._engine = self._build_engine(config=config)
        self._paused_streams: set[str] = set()

    @property
    def mode(self) -> str:
        return self._config.mode

    def reply(self, request: ChatRequest) -> AssistantMessage:
        reply_text = self._engine.generate(request.messages)
        return AssistantMessage(id=str(uuid4()), content=reply_text)

    def iter_chunks(self, text: str, chunk_size: int = 8) -> list[str]:
        if chunk_size <= 0:
            return [text]
        if not text:
            return [""]
        return [text[idx : idx + chunk_size] for idx in range(0, len(text), chunk_size)]

    def stream_reply(self, request: ChatRequest) -> Iterator[str]:
        """Stream tokens/chunks from the underlying engine when available.

        Falls back to chunking a synchronous reply when streaming is not supported.
        """
        stream_id = request.streamId
        engine = self._engine
        try:
            # If engine exposes a streaming interface, delegate to it.
            if hasattr(engine, "stream"):
                for chunk in engine.stream(request.messages):
                    if stream_id and stream_id in self._paused_streams:
                        break
                    yield chunk

            # Fallback: synchronous generation then chunking
            else:
                assistant = self.reply(request)
                for chunk in self.iter_chunks(assistant.content):
                    if stream_id and stream_id in self._paused_streams:
                        break
                    yield chunk
        finally:
            if stream_id:
                self._paused_streams.discard(stream_id)

    def stream_frames(self, request: ChatRequest, message_id: str) -> Iterator[StreamFrame]:
        """Wrap streaming output into protocol V1 structured frames."""
        framer = StreamFramer(message_id=message_id)
        try:
            for chunk in self.stream_reply(request):
                yield from framer.push_text(chunk)
        except Exception as exc:
            yield framer.error(str(exc))
        finally:
            trace = self._collect_skill_trace()
            if trace:
                yield framer.meta({"skillTrace": trace})
            yield from framer.finalize()

    def supports_streaming(self) -> bool:
        return hasattr(self._engine, "stream")

    def pause_stream(self, stream_id: str) -> None:
        if stream_id:
            self._paused_streams.add(stream_id)

    def _collect_skill_trace(self) -> list[dict[str, object]]:
        getter = getattr(self._engine, "get_last_trace", None)
        if not callable(getter):
            return []

        try:
            trace = getter()
        except Exception:
            return []

        if not isinstance(trace, list):
            return []

        safe_trace: list[dict[str, object]] = []
        for item in trace:
            if isinstance(item, dict):
                safe_trace.append(item)
        return safe_trace

    @staticmethod
    def _build_engine(config: AppConfig) -> ChatEngine:
        mode = config.mode
        if mode == "frame":
            return FrameChatEngine()
        if mode == "openai":
            return SimpleOpenAIEngine()
        if mode == "skill_rag":
            return SkillRagChatEngine(
                knowledge_base_root=config.knowledge_base_root,
                knowledge_chunks_root=config.knowledge_chunks_root,
                knowledge_summary_root=config.knowledge_summary_root,
                top_k=config.skill_top_k,
                max_skill_calls=config.skill_max_calls,
            )
        return MockChatEngine()
