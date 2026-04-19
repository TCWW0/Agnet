from __future__ import annotations

from uuid import uuid4
from typing import Iterator

from src.config import AppConfig
from src.engines import ChatEngine, FrameChatEngine, MockChatEngine, SimpleOpenAIEngine
from src.schemas import AssistantMessage, ChatRequest
from src.stream_framing import StreamFrame, StreamFramer


class ChatService:
    """Application service for chat reply and chunk streaming."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._engine = self._build_engine(config.mode)

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
        engine = self._engine
        # If engine exposes a streaming interface, delegate to it.
        if hasattr(engine, "stream"):
            yield from engine.stream(request.messages)

        # Fallback: synchronous generation then chunking
        else:
            assistant = self.reply(request)
            for chunk in self.iter_chunks(assistant.content):
                yield chunk

    def stream_frames(self, request: ChatRequest, message_id: str) -> Iterator[StreamFrame]:
        """Wrap streaming output into protocol V1 structured frames."""
        framer = StreamFramer(message_id=message_id)
        try:
            for chunk in self.stream_reply(request):
                yield from framer.push_text(chunk)
        except Exception as exc:
            yield framer.error(str(exc))
        finally:
            yield from framer.finalize()

    def supports_streaming(self) -> bool:
        return hasattr(self._engine, "stream")

    @staticmethod
    def _build_engine(mode: str) -> ChatEngine:
        if mode == "frame":
            return FrameChatEngine()
        if mode == "openai":
            return SimpleOpenAIEngine()
        return MockChatEngine()
