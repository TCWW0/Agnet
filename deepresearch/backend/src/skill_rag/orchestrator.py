from __future__ import annotations

import time

from .models import SkillCallInput, SkillOrchestrationResult, SkillTrace
from .registry import SkillRegistry
from .router import DeterministicSkillRouter


class SkillRagOrchestrator:
    def __init__(
        self,
        registry: SkillRegistry,
        router: DeterministicSkillRouter,
        max_skill_calls: int = 3,
        top_k: int = 4,
    ) -> None:
        self._registry = registry
        self._router = router
        self._max_skill_calls = max_skill_calls
        self._top_k = top_k

    def run(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
        conversation_id: str | None = None,
    ) -> SkillOrchestrationResult:
        history = history or []
        decision = self._router.route(query)

        execution_order = [decision.primary_skill_id, *decision.fallback_skill_ids]
        execution_order = execution_order[: self._max_skill_calls]

        all_evidence = []
        traces: list[SkillTrace] = []

        for idx, skill_id in enumerate(execution_order, start=1):
            if not self._registry.has(skill_id):
                continue

            call_input = SkillCallInput(
                query=query,
                history=history,
                conversation_id=conversation_id,
                options={"top_k": self._top_k},
            )

            started = time.perf_counter()
            result = self._registry.get(skill_id).run(call_input)
            elapsed_ms = int((time.perf_counter() - started) * 1000)

            all_evidence.extend(result.evidence)
            traces.append(
                SkillTrace(
                    step=idx,
                    skill_id=skill_id,
                    decision_reason=decision.reason if idx == 1 else "fallback",
                    evidence_count=len(result.evidence),
                    elapsed_ms=elapsed_ms,
                    meta=result.meta,
                )
            )

            if len(all_evidence) >= self._top_k:
                break

        dedup_evidence = []
        seen_paths: set[str] = set()
        for evidence in sorted(all_evidence, key=lambda item: item.score, reverse=True):
            if evidence.source_path in seen_paths:
                continue
            dedup_evidence.append(evidence)
            seen_paths.add(evidence.source_path)
            if len(dedup_evidence) >= self._top_k:
                break

        answer = self._build_answer(query=query, evidence=dedup_evidence)
        citations = [item.source_path for item in dedup_evidence]

        return SkillOrchestrationResult(answer=answer, citations=citations, traces=traces)

    @staticmethod
    def _build_answer(query: str, evidence: list) -> str:
        if not evidence:
            return (
                "I could not find grounded evidence from the current knowledge corpus. "
                "Please refine the query with a clearer product/region/file hint."
            )

        lines = [
            "Proposed answer based on retrieved evidence:",
            f"Question: {query}",
            "",
            "Evidence summary:",
        ]
        for idx, item in enumerate(evidence, start=1):
            compact = " ".join(item.snippet.split())
            if len(compact) > 240:
                compact = compact[:240] + "..."
            lines.append(f"{idx}. {compact}")

        lines.append("")
        lines.append("Citations:")
        for idx, item in enumerate(evidence, start=1):
            lines.append(f"{idx}. {item.source_path}")

        return "\n".join(lines)
