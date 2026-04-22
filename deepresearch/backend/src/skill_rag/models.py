from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SkillRiskLevel = Literal["read_only", "constrained_write", "sensitive"]


class SkillCallInput(BaseModel):
    query: str = Field(min_length=1)
    conversation_id: str | None = None
    history: list[dict[str, str]] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class SkillEvidence(BaseModel):
    source_path: str
    snippet: str
    score: float = 0.0


class SkillResult(BaseModel):
    skill_id: str
    summary: str
    evidence: list[SkillEvidence] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class SkillTrace(BaseModel):
    step: int
    skill_id: str
    decision_reason: str
    evidence_count: int
    elapsed_ms: int
    meta: dict[str, Any] = Field(default_factory=dict)


class SkillRouteDecision(BaseModel):
    primary_skill_id: str
    reason: str
    fallback_skill_ids: list[str] = Field(default_factory=list)


class SkillOrchestrationResult(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    traces: list[SkillTrace] = Field(default_factory=list)
