from __future__ import annotations

from .base import BaseSkill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.skill_id] = skill

    def get(self, skill_id: str) -> BaseSkill:
        return self._skills[skill_id]

    def has(self, skill_id: str) -> bool:
        return skill_id in self._skills

    def list_ids(self) -> list[str]:
        return list(self._skills.keys())
