from __future__ import annotations

from datetime import datetime, timezone
import json
from threading import Lock
from typing import Iterator
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.config import AppConfig
from src.schemas import ChatRequest, ChatResponse, HealthResponse, PauseStreamRequest, PauseStreamResponse
from src.service import ChatService


def _to_sse(data: str, event: str | None = None) -> str:
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    lines.extend(f"data: {line}" for line in data.splitlines() or [""])
    return "\n".join(lines) + "\n\n"


_paused_stream_ids: set[str] = set()
_paused_stream_lock = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _mark_stream_paused(stream_id: str) -> None:
    with _paused_stream_lock:
        _paused_stream_ids.add(stream_id)


def _is_stream_paused(stream_id: str | None) -> bool:
    if not stream_id:
        return False
    with _paused_stream_lock:
        return stream_id in _paused_stream_ids


def _clear_stream_pause(stream_id: str | None) -> None:
    if not stream_id:
        return
    with _paused_stream_lock:
        _paused_stream_ids.discard(stream_id)


def _build_done_frame(message_id: str, seq: int, meta: dict[str, object] | None = None) -> dict[str, object]:
    frame: dict[str, object] = {
        "protocolVersion": "1.0",
        "type": "done",
        "messageId": message_id,
        "seq": seq,
        "role": "assistant",
        "timestamp": _now_iso(),
    }
    if meta is not None:
        frame["meta"] = meta
    return frame


config = AppConfig.from_env()
service = ChatService(config=config)

app = FastAPI(title="DeepResearch Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", mode=service.mode)


@app.post("/api/v1/chat", response_model=ChatResponse)
def post_chat(request: ChatRequest) -> ChatResponse:
    assistant = service.reply(request)
    return ChatResponse(message=assistant)


@app.post("/api/v1/chat/stream")
def post_chat_stream(request: ChatRequest) -> StreamingResponse:
    assistant_id = str(uuid4())
    stream_id = request.streamId or f"stream-{assistant_id}"

    def stream() -> Iterator[str]:
        if _is_stream_paused(stream_id):
            paused_frame = _build_done_frame(
                message_id=assistant_id,
                seq=1,
                meta={"paused": True, "streamId": stream_id},
            )
            yield _to_sse(json.dumps(paused_frame, ensure_ascii=False), event="done")
            _clear_stream_pause(stream_id)
            return

        seq = 0
        frame_iter = service.stream_frames(request=request, message_id=assistant_id)
        try:
            for frame in frame_iter:
                current_seq = frame.get("seq")
                if isinstance(current_seq, int):
                    seq = current_seq
                else:
                    seq += 1

                if _is_stream_paused(stream_id):
                    paused_frame = _build_done_frame(
                        message_id=assistant_id,
                        seq=seq + 1,
                        meta={"paused": True, "streamId": stream_id},
                    )
                    yield _to_sse(json.dumps(paused_frame, ensure_ascii=False), event="done")
                    break

                event = str(frame.get("type", "chunk"))
                payload = json.dumps(frame, ensure_ascii=False)
                yield _to_sse(payload, event=event)
        finally:
            close_fn = getattr(frame_iter, "close", None)
            if callable(close_fn):
                close_fn()
            _clear_stream_pause(stream_id)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/v1/chat/stream/pause", response_model=PauseStreamResponse)
def post_chat_stream_pause(request: PauseStreamRequest) -> PauseStreamResponse:
    _mark_stream_paused(request.streamId)
    return PauseStreamResponse(status="ok", streamId=request.streamId)


@app.get("/api/v1/chat/stream")
def get_chat_stream_probe(conversationId: str = "") -> StreamingResponse:
    """Compatibility endpoint for EventSource probing from current frontend draft.

    NOTE: This endpoint is a lightweight probe for EventSource-only frontends. The
    recommended streaming contract is to POST `/api/v1/chat/stream` and consume a
    `text/event-stream` or chunked response (fetch + ReadableStream) carrying the
    message chunks. EventSource only supports GET and therefore cannot carry a
    request body; this probe exists for compatibility only.
    """

    def stream() -> Iterator[str]:
        hint = "stream endpoint is ready"
        if conversationId:
            hint = f"stream endpoint is ready for conversation {conversationId}"
        yield _to_sse(hint, event="info")
        yield _to_sse(json.dumps({"done": True}), event="done")

    return StreamingResponse(stream(), media_type="text/event-stream")
