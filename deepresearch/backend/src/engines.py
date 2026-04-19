from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence, Iterator
from queue import Queue
import sys
import os

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from typing import cast, Iterable, Any

from src.schemas import ChatMessage


class ChatEngine(Protocol):
    """Contract for chat generation engines."""

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        ...

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        ...


class MockChatEngine:
    """Deterministic local engine for frontend/backend联调."""

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        latest_user = ""
        for msg in reversed(messages):
            if msg.role == "user":
                latest_user = msg.content
                break
        if not latest_user:
            return "(mock) 未检测到用户输入。"
        return f"(mock) 我收到了你的消息：{latest_user}"

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        text = self.generate(messages)
        # simple chunking for mock streaming (per 8 chars)
        chunk_size = 8
        if not text:
            yield ""
            return
        for idx in range(0, len(text), chunk_size):
            yield text[idx : idx + chunk_size]

class SimpleOpenAIEngine:
    """Minimal OpenAI-backed engine for quick integration testing.

    This engine uses the `openai` Python client directly and supports
    both sync `generate` and streaming `stream` paths. It reads model
    configuration from environment variables: `LLM_MODEL_ID`,
    `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_ORGANIZATION`.
    """

    def __init__(self) -> None:
        model = os.getenv("LLM_MODEL_ID", "gpt-4o-mini")
        api_key = os.getenv("LLM_API_KEY", "")
        org = os.getenv("LLM_ORGANIZATION", "")
        base_url = os.getenv("LLM_BASE_URL", "")

        # Initialize OpenAI client. If API key is empty, client may still
        # be constructed but calls will fail at runtime; tests should
        # guard against missing key.
        self._client = OpenAI(organization=org, api_key=api_key, base_url=base_url)
        self._model = model

    def _messages_to_payload(self, messages: Sequence[ChatMessage]) -> list[dict]:
        payload: list[dict] = []
        for m in messages:
            payload.append({"role": m.role, "content": m.content})
        return payload

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        payload = self._messages_to_payload(messages)
        try:
            # Cast payload to the typed alias expected by the OpenAI client
            typed_messages = cast(Iterable[ChatCompletionMessageParam], payload)
            resp = self._client.chat.completions.create(model=self._model, messages=typed_messages, max_tokens=512)
            # Try common response shapes
            if hasattr(resp, "choices") and resp.choices:
                first = resp.choices[0]
                # new style: first.message.content
                message = getattr(first, "message", None)
                if message is not None:
                    content = getattr(message, "content", None)
                    if isinstance(content, str):
                        return content
                    # Some clients nest content under dict/list forms; try str() fallback
                    if content is not None:
                        return str(content)

                # fallback: try .text attribute if present
                text_attr = getattr(first, "text", None)
                if isinstance(text_attr, str):
                    return text_attr
        except Exception:
            # keep failure silent for integration dev (caller should handle)
            pass
        return ""

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        payload = self._messages_to_payload(messages)
        try:
            typed_messages = cast(Iterable[ChatCompletionMessageParam], payload)
            stream_iter = self._client.chat.completions.create(model=self._model, messages=typed_messages, stream=True)
            for chunk in stream_iter:
                # Attempt to extract the delta text from common shapes
                try:
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    choice = choices[0]
                    # Try streaming delta (newer shape)
                    delta = getattr(choice, "delta", None)
                    text = None
                    if delta is not None:
                        # delta may be mapping-like or object-like
                        get_fn = getattr(delta, "get", None)
                        if callable(get_fn):
                            text = get_fn("content")
                        else:
                            text = getattr(delta, "content", None)
                    if not text:
                        # Fallbacks: older shapes
                        text = getattr(choice, "text", None)
                        if not text:
                            message = getattr(choice, "message", None)
                            if message is not None:
                                text = getattr(message, "content", None)
                    if text:
                        yield str(text)
                except Exception:
                    continue
        except Exception:
            # On any streaming error, fall back to empty iterator
            return


class FrameChatEngine:
    """Adapter engine that delegates generation to frame.core.BaseLLM."""

    def __init__(self) -> None:
        self._ensure_project_root_in_path()

        from frame.core.base_llm import BaseLLM
        from frame.core.config import LLMConfig

        self._llm = BaseLLM(LLMConfig.from_env())

    def generate(self, messages: Sequence[ChatMessage]) -> str:
        from frame.core.message import Message, UserTextMessage

        frame_messages: list[Message] = []
        for msg in messages:
            if msg.role == "user":
                frame_messages.append(UserTextMessage(content=msg.content))
            else:
                frame_messages.append(Message(role=msg.role, content=msg.content))

        response_messages = self._llm.invoke(messages=frame_messages, tools=[])
        text_parts = [msg.content for msg in response_messages if getattr(msg, "type", "") == "text"]
        if not text_parts:
            return ""
        return "".join(text_parts)

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        from frame.core.message import Message, UserTextMessage

        import queue
        import threading

        frame_messages: list[Message] = []
        for msg in messages:
            if msg.role == "user":
                frame_messages.append(UserTextMessage(content=msg.content))
            else:
                frame_messages.append(Message(role=msg.role, content=msg.content))

        q: Queue[object] = queue.Queue()
        _SENTINEL = object()

        def on_token_callback(text: str) -> None:
            if text:
                q.put(text)

        def _invoke_stream() -> None:
            try:
                # delegate to BaseLLM streaming API
                self._llm.invoke_streaming(messages=frame_messages, tools=[], on_token_callback=on_token_callback)
            finally:
                q.put(_SENTINEL)

        t = threading.Thread(target=_invoke_stream, daemon=True)
        t.start()

        while True:
            item = q.get()
            if item is _SENTINEL:
                break
            # Narrow to str to satisfy static type checkers (Pylance).
            if not isinstance(item, str):
                # ignore unexpected non-str payloads
                continue
            yield item

        t.join(timeout=1)

    @staticmethod
    def _ensure_project_root_in_path() -> None:
        project_root = Path(__file__).resolve().parents[3]
        root_str = str(project_root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
