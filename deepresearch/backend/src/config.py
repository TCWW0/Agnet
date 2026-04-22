from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bounded_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


@dataclass(frozen=True)
class AppConfig:
    """Runtime settings for backend service."""

    mode: str
    cors_origins: list[str]
    knowledge_base_root: Path
    knowledge_chunks_root: Path
    knowledge_summary_root: Path
    skill_top_k: int
    skill_max_calls: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        repo_root = Path(__file__).resolve().parents[3]

        mode = os.getenv("DEEPRESEARCH_CHAT_MODE", "mock").strip().lower() or "mock"
        raw_origins = os.getenv("DEEPRESEARCH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

        knowledge_base_root = Path(
            os.getenv("DEEPRESEARCH_KB_ROOT", str(repo_root / "Knowledge-Base"))
        ).resolve()
        knowledge_chunks_root = Path(
            os.getenv("DEEPRESEARCH_KB_CHUNKS_ROOT", str(repo_root / "Knowledge-Base-Chunks"))
        ).resolve()
        knowledge_summary_root = Path(
            os.getenv("DEEPRESEARCH_KB_SUMMARY_ROOT", str(repo_root / "Knowledge-Base-File-Summary"))
        ).resolve()

        skill_top_k = _bounded_int_env("DEEPRESEARCH_SKILL_TOP_K", default=4, min_value=1, max_value=20)
        skill_max_calls = _bounded_int_env("DEEPRESEARCH_SKILL_MAX_CALLS", default=3, min_value=1, max_value=8)

        return cls(
            mode=mode,
            cors_origins=cors_origins,
            knowledge_base_root=knowledge_base_root,
            knowledge_chunks_root=knowledge_chunks_root,
            knowledge_summary_root=knowledge_summary_root,
            skill_top_k=skill_top_k,
            skill_max_calls=skill_max_calls,
        )
