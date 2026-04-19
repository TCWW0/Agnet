from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# Skip integration tests unless a real LLM key is configured.
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("LLM_API_KEY", ""))
if not LLM_API_KEY or LLM_API_KEY.strip() == "" or LLM_API_KEY == "local_no_key":
    pytest.skip("No LLM_API_KEY configured; skipping frame/openai LLM integration tests", allow_module_level=True)

# Use frame mode for these tests (FrameChatEngine -> BaseLLM) or 'openai' if preferred.
os.environ["DEEPRESEARCH_CHAT_MODE"] = os.getenv("DEEPRESEARCH_CHAT_MODE", "frame")

from src.main import app


client = TestClient(app)


def test_frame_chat_sync() -> None:
    payload = {"messages": [{"id": "1", "role": "user", "content": "请简单介绍你自己"}]}
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["role"] == "assistant"
    assert isinstance(body["message"]["content"], str)
    assert len(body["message"]["content"]) > 0


def test_frame_chat_stream() -> None:
    payload = {"messages": [{"id": "1", "role": "user", "content": "请流式发送一段示例文本"}]}
    response = client.post("/api/v1/chat/stream", json=payload)
    assert response.status_code == 200
    assert "event: chunk" in response.text