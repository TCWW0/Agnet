from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ChatRole = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    id: str | None = None
    role: ChatRole
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    conversationId: str | None = None
    streamId: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list, min_length=1)


class AssistantMessage(BaseModel):
    id: str
    role: Literal["assistant"] = "assistant"
    content: str


class ChatResponse(BaseModel):
    message: AssistantMessage


class HealthResponse(BaseModel):
    status: Literal["ok"]
    mode: str


class PauseStreamRequest(BaseModel):
    streamId: str = Field(min_length=1)
    conversationId: str | None = None


class PauseStreamResponse(BaseModel):
    status: Literal["ok"]
    streamId: str
