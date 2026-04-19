from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Runtime settings for backend service."""

    mode: str
    cors_origins: list[str]

    @classmethod
    def from_env(cls) -> "AppConfig":
        mode = os.getenv("DEEPRESEARCH_CHAT_MODE", "mock").strip().lower() or "mock"
        raw_origins = os.getenv("DEEPRESEARCH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
        return cls(mode=mode, cors_origins=cors_origins)
