from __future__ import annotations

from abc import ABC, abstractmethod

from .models import SkillCallInput, SkillResult, SkillRiskLevel


class BaseSkill(ABC):
    skill_id: str
    intent: str
    risk_level: SkillRiskLevel = "read_only"

    @abstractmethod
    def run(self, inp: SkillCallInput) -> SkillResult:
        raise NotImplementedError()
