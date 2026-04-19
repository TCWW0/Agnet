from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Iterator, Sequence

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# Ensure tests use deterministic local engine.
os.environ["DEEPRESEARCH_CHAT_MODE"] = "mock"

from src.main import app
from src.main import service
from src.schemas import ChatMessage


client = TestClient(app)


def _parse_sse_events(raw_text: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in [part for part in raw_text.split("\n\n") if part.strip()]:
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            if line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        if not data_lines:
            continue
        payload = json.loads("\n".join(data_lines))
        events.append((event_name, payload))
    return events


def test_health_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"


def test_post_chat_returns_assistant_message() -> None:
    payload = {
        "messages": [
            {"id": "1", "role": "user", "content": "你好，后端"}
        ]
    }
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["message"]["role"] == "assistant"
    assert "你好，后端" in body["message"]["content"]


def test_post_chat_stream_sends_done_event() -> None:
    payload = {
        "messages": [
            {"id": "1", "role": "user", "content": "请流式回复"}
        ]
    }
    response = client.post("/api/v1/chat/stream", json=payload)
    assert response.status_code == 200

    events = _parse_sse_events(response.text)
    assert events

    event_names = [name for name, _ in events]
    assert "chunk" in event_names
    assert "done" in event_names

    message_ids = {
        payload["messageId"]
        for _, payload in events
        if isinstance(payload.get("messageId"), str)
    }
    assert len(message_ids) == 1

    seq_values = [payload["seq"] for _, payload in events if isinstance(payload.get("seq"), int)]
    assert seq_values == sorted(seq_values) # type: ignore[comparison-overlap]

    for event_name, payload in events:
        assert payload["protocolVersion"] == "1.0"
        assert payload["type"] == event_name


class _MarkerEngine:
    def generate(self, messages: Sequence[ChatMessage]) -> str:
        return "第一段<|PARA|>第二段"

    def stream(self, messages: Sequence[ChatMessage]) -> Iterator[str]:
        yield "第一段<|PA"
        yield "RA|>第二段"


def test_post_chat_stream_emits_paragraph_frames() -> None:
    payload = {
        "messages": [
            {"id": "1", "role": "user", "content": "请返回两段"}
        ]
    }
    original_engine = service._engine
    service._engine = _MarkerEngine()  # type: ignore[assignment]
    try:
        response = client.post("/api/v1/chat/stream", json=payload)
    finally:
        service._engine = original_engine

    assert response.status_code == 200
    events = _parse_sse_events(response.text)

    paragraph_texts = [
        event_payload["text"]
        for event_name, event_payload in events
        if event_name == "paragraph" and isinstance(event_payload.get("text"), str)
    ]
    assert paragraph_texts == ["第一段", "第二段"]

    done_payloads = [event_payload for event_name, event_payload in events if event_name == "done"]
    assert len(done_payloads) == 1
    done_meta = done_payloads[0].get("meta")
    assert isinstance(done_meta, dict)
    assert done_meta.get("paragraphCount") == 2


def test_post_chat_stream_pause_endpoint_and_paused_done_event() -> None:
    stream_id = "stream_pause_test"
    pause_response = client.post(
        "/api/v1/chat/stream/pause",
        json={"streamId": stream_id, "conversationId": "conv_pause"},
    )
    assert pause_response.status_code == 200
    assert pause_response.json() == {"status": "ok", "streamId": stream_id}

    stream_payload = {
        "conversationId": "conv_pause",
        "streamId": stream_id,
        "messages": [
            {"id": "1", "role": "user", "content": "请暂停当前流"}
        ],
    }
    stream_response = client.post("/api/v1/chat/stream", json=stream_payload)
    assert stream_response.status_code == 200

    events = _parse_sse_events(stream_response.text)
    assert events

    done_payloads = [payload for event_name, payload in events if event_name == "done"]
    assert done_payloads
    done_meta = done_payloads[0].get("meta")
    assert isinstance(done_meta, dict)
    assert done_meta.get("paused") is True
    assert done_meta.get("streamId") == stream_id
