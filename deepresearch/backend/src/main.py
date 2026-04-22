from __future__ import annotations

import json
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

    def stream() -> Iterator[str]:
        for frame in service.stream_frames(request=request, message_id=assistant_id):
            event = str(frame.get("type", "chunk"))
            payload = json.dumps(frame, ensure_ascii=False)
            yield _to_sse(payload, event=event)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/v1/chat/stream/pause", response_model=PauseStreamResponse)
def post_chat_stream_pause(request: PauseStreamRequest) -> PauseStreamResponse:
    service.pause_stream(request.streamId)
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
