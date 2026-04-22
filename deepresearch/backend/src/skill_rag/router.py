from __future__ import annotations

import re

from .models import SkillRouteDecision


_PATH_PATTERN = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:md|txt|json)", re.IGNORECASE)


class DeterministicSkillRouter:
    """A predictable first-stage router used before any LLM-based routing."""

    def route(self, query: str) -> SkillRouteDecision:
        normalized = query.strip().lower()
        if not normalized:
            return SkillRouteDecision(
                primary_skill_id="map_skill",
                reason="empty_query_fallback",
                fallback_skill_ids=["vector_retrieve_skill"],
            )

        if _PATH_PATTERN.search(query) or "knowledge-base/" in normalized:
            return SkillRouteDecision(
                primary_skill_id="path_retrieve_skill",
                reason="explicit_path_detected",
                fallback_skill_ids=["map_skill", "vector_retrieve_skill"],
            )

        token_count = len(query.split())
        if token_count >= 12 or len(query) >= 64:
            return SkillRouteDecision(
                primary_skill_id="vector_retrieve_skill",
                reason="long_or_complex_query",
                fallback_skill_ids=["map_skill"],
            )

        return SkillRouteDecision(
            primary_skill_id="map_skill",
            reason="default_summary_navigation",
            fallback_skill_ids=["vector_retrieve_skill"],
        )
