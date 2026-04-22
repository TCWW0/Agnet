<!-- markdownlint-disable-file -->

# Task Research Notes: Skill-RAG Project Landing for frame + deepresearch

## Research Executed

### File Analysis

- /root/agent/frame/core/llm_orchestrator.py
  - Verified `ToolCallMode.AUTO` multi-round loop already exists (`_execute_tool_calls` + `max_tool_rounds`) and can host Skill-RAG execution without rewriting core invoke flow.
- /root/agent/frame/core/base_llm.py
  - Verified typed invocation policy already supports tool-mode switching and streaming callbacks, which can carry skill traces and token events.
- /root/agent/frame/tool/base.py
  - Verified tool schema contract (`ToolDesc` + OpenAI function schema mapping) and unified execution error handling are available for skill adaptation.
- /root/agent/frame/tool/register.py
  - Verified registry abstraction exists but is list-based and currently lacks typed capability/risk metadata needed for skill-level governance.
- /root/agent/frame/memory/base.py
  - Verified retrieval+tool dual path (`AgentMemoryHooks` + `MemoryToolFacade`) provides a proven pattern for adding a parallel Skill-RAG facade.
- /root/agent/frame/evaluation/harness.py
  - Verified dataset→executor→grader→report pipeline is production-usable for offline regression gates.
- /root/agent/frame/evaluation/models.py
  - Verified evaluation model supports arm-based comparisons and thresholds, suitable for A/B/C migration of no-skill vs skillized variants.
- /root/agent/deepresearch/backend/src/engines.py
  - Verified `FrameChatEngine` currently calls `BaseLLM` with `tools=[]`; no current path enables knowledge tools/skills.
- /root/agent/deepresearch/backend/src/main.py
  - Verified `/api/v1/chat` and `/api/v1/chat/stream` exist with SSE framing; public API prefix already compliant.
- /root/agent/deepresearch/backend/src/stream_framing.py
  - Verified protocol includes `meta` frame type, but current service path mainly emits `chunk/paragraph/done/error`; `meta` is available for skill trace streaming.
- /root/agent/deepresearch/backend/src/schemas.py
  - Verified `PauseStreamRequest/Response` models exist, but route implementation was not found in backend router.
- /root/agent/deepresearch/front/src/services/agentClient.ts
  - Verified frontend stream parser already supports typed SSE frames and can consume additional protocol metadata with backward-compatible fallback.
- /root/agent/deepresearch/front/src/pages/ChatPage.tsx
  - Verified API payload currently sends only latest user message (`msgsForApi = [userMsg]`), which blocks multi-turn retrieval quality.
- /root/agent/deepresearch/front/src/store/chatStore.ts
  - Verified local conversation/session store already exists and can supply full message history for retrieval-aware backend requests.
- /root/agent/deepresearch/docx/20260418-fe-be-contract-v1.md
  - Verified existing V1 contract aligns with `/api/v1` and streaming frame taxonomy; changes should preserve backward compatibility.
- /root/agent/deepresearch/front/docs/frontend-summary.md
  - Verified frontend architecture is CSS-variable and Zustand centered; service-layer changes are preferred over component-wide rewrites.

### Code Search Results

- skill|Skill|registry|router|vector|embedding|knowledge base|retrieve_files (frame/** + deepresearch/**)
  - No first-class Skill-RAG modules in current repository; only generic tool registry and memory retrieval capabilities were found.
- /api/v1/chat/stream/pause|pauseStream|PauseStreamRequest|PauseStreamResponse (deepresearch/**)
  - Matches found in frontend caller, backend README, and backend schema; no backend route handler match found, indicating doc/schema/implementation drift.
- conversationId|session_id|session|history|store (deepresearch/backend/src/**)
  - Backend currently does not persist conversation history by `conversationId`; only probe endpoint reads `conversationId` query.
- tool_mode|max_tool_rounds|ToolCallMode|AUTO (frame/core/**)
  - Confirmed orchestration policy and bounded tool loop are already present and can be reused for skill routing control.

### External Research

- #githubRepo:"vibrantlabsai/ragas ToolCallAccuracy ToolCallF1 AgentGoalAccuracy metrics collections API"
  - Verified modern collections API exists for `ToolCallAccuracy`, `ToolCallF1`, and `AgentGoalAccuracy` and legacy API is marked deprecated.
  - Verified `ToolCallAccuracy` supports strict/flexible order and argument-level scoring with coverage penalties.
  - Verified `ToolCallF1` provides softer precision/recall signal for iterative onboarding.
- #githubRepo:"confident-ai/deepeval contextual precision recall faithfulness tool correctness goal accuracy"
  - Verified retriever/generator metric split and five core RAG metrics are operationalized in evaluation workflows.
  - Verified agentic dimensions include tool correctness, argument correctness, and goal/task-oriented metrics.
  - Verified threshold-driven pass/fail usage pattern for CI-style regression checks.
- #githubRepo:"truera/trulens rag triad context relevance groundedness answer relevance"
  - Verified RAG Triad framing (context relevance, groundedness, answer relevance) and selector-based instrumentation patterns.
  - Verified reference-free triad positioning for enterprise scenarios with limited gold labels.
- #githubRepo:"openai/openai-cookbook evals tools evaluation regression"
  - Verified practical tool-call grading patterns and reusable harness structures for deterministic + rubric-based evaluation.
  - Verified eval run lifecycle and artifact-driven validation loops applicable to CI gating.
- #fetch:https://developers.openai.com/api/docs/guides/tools-skills
  - Verified skills are versioned bundles (`SKILL.md` + files) with hosted/local execution differences and strict validation limits.
  - Verified safety guidance: developer-curated integration, no open end-user skill marketplace, and approval gates for sensitive actions.
  - Verified version pointers (`default_version`, `latest_version`) support controlled rollout.
- #fetch:https://developers.openai.com/api/docs/guides/evals
  - Verified eval lifecycle: define schema/criteria, upload JSONL, create asynchronous runs, inspect per-criteria outcomes and usage.
  - Verified run status and webhook integration pattern for automation.
- #fetch:https://developers.openai.com/api/docs/guides/evaluation-best-practices
  - Verified eval-driven development recommendation and architecture-specific eval placement (single-turn/workflow/agent/multi-agent).
  - Verified mixed evaluator strategy (metric + human + LLM-as-judge) is recommended for production reliability.
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
  - Verified context precision definition and ranking-quality formula; collections API is current path.
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/
  - Verified claim-based context recall definition requiring reference/grounding proxy.
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
  - Verified faithfulness definition as fraction of supported claims in retrieved context.
- #fetch:https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/
  - Verified plugin/function authoring guidance: semantic descriptions, parameter clarity, controlled tool count, and function granularity trade-off.
- #fetch:https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/using-data-retrieval-functions-for-rag
  - Verified semantic vs classic retrieval complementarity and recommendation to combine by query type.
  - Verified security recommendations: user-token authorization and avoiding sensitive-data duplication in vector stores.
- #fetch:https://www.anthropic.com/engineering
  - Anthropic engineering posts emphasize harness reliability, infrastructure noise control, and iterative eval loops for agent systems.
  - Tool-use and agent-skill related engineering artifacts show production focus on controllability over one-shot quality.
  - Multi-step evaluation and robustness testing are repeatedly treated as first-class engineering concerns.

### Project Conventions

- Standards referenced: `frame` typed orchestration + tool schema style, `deepresearch` `/api/v1` streaming contract, existing evaluation and test layout.
- Instructions followed: `.github/instructions/` directory is absent in this repository; conventions were inferred from executable code, existing docs under `deepresearch/docx`, and skill guardrails.

## Key Discoveries

### Project Structure

Current repository is suitable for incremental Skill-RAG landing because it already has all three primitives needed for controlled evolution:

1. Frame runtime primitive: `BaseLLM` + `LLMInvocationOrchestrator` already support bounded auto tool execution loops.
2. Tool contract primitive: `BaseTool` + OpenAI schema mapping already provide a stable, typed action boundary.
3. Service/UI primitive: deepresearch backend/frontend already implement `/api/v1` streaming and structured frame parsing.

Main blockers are not foundational; they are adaptation gaps:

- No skill registry/router abstraction above current tool registry.
- No retrieval skill family (path/vector/map/synthesis/verifier) in `frame`.
- DeepResearch backend currently disables tools when calling frame engine.
- Frontend sends only latest user message, which weakens multi-turn retrieval quality.
- Pause endpoint drift (frontend/backend README/schema mention exists, backend route missing).

### Implementation Patterns

Observed patterns that should be reused directly:

- Orchestrator-first execution: put routing logic before tool execution, not inside tool code.
- Schema-first tools: each capability exposes explicit parameter schema via `ToolDesc`.
- Streaming resilience: protocol already tolerates mixed frame quality via parser fallbacks.
- Eval-first iteration: existing harness supports controlled arm comparisons and threshold checks.

Critical adaptation insight:

- Skill-RAG should be implemented as a typed capability layer on top of existing `BaseTool` + orchestrator, not as a parallel agent runtime. This avoids split execution semantics and preserves existing tests.

### Complete Examples

```python
# Source-adapted for current repository patterns.
# Goal: add skill routing without replacing frame core orchestrator.

from dataclasses import dataclass
from typing import Any, Dict, List

from frame.tool.base import BaseTool, ToolResponse
from frame.core.llm_types import InvocationPolicy, InvocationRequest, ToolCallMode


@dataclass
class SkillRoute:
    skill_name: str
    arguments: Dict[str, Any]


class SkillRouter:
    def select(self, user_query: str, history: List[dict]) -> SkillRoute:
        # Deterministic first, LLM-based routing can be introduced later.
        if "/" in user_query or "path" in user_query.lower():
            return SkillRoute("path_retrieve_skill", {"query": user_query})
        if len(user_query) > 48:
            return SkillRoute("vector_retrieve_skill", {"query": user_query, "top_k": 6})
        return SkillRoute("map_skill", {"query": user_query})


class SkillToolAdapter(BaseTool):
    # Adapter keeps compatibility with existing BaseTool execution + schema path.
    def __init__(self, name: str, impl) -> None:
        super().__init__(name=name, description=f"Skill adapter: {name}")
        self._impl = impl

    @classmethod
    def desc(cls):
        raise NotImplementedError("Use concrete adapters with explicit schema")

    def valid_paras(self, params: Dict[str, Any]) -> bool:
        return isinstance(params, dict)

    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        result = self._impl.run(params)
        return ToolResponse(tool_name=self.name, status="success", output=result)


def run_skill_rag_turn(llm, messages, tools):
    policy = InvocationPolicy(tool_mode=ToolCallMode.AUTO, max_tool_rounds=4)
    request = InvocationRequest(messages=messages, tools=tools, policy=policy, stream=True)
    return llm.orchestrator_.invoke_streaming(request=request)
```

### API and Schema Documentation

Landing-compatible API contract (recommended extension over existing endpoints):

- Keep existing: `POST /api/v1/chat`, `POST /api/v1/chat/stream`, `GET /api/v1/health`.
- Extend stream frames with optional `meta.skillTrace` payload (no breaking changes).
- Add explicit retrieval diagnostics endpoint for offline/debug use:
  - `POST /api/v1/knowledge/query`
  - Request:
    - `conversationId`: string | null
    - `query`: string
    - `history`: array of chat messages
    - `options`: `{ mode: "hybrid", top_k: int, return_trace: bool }`
  - Response:
    - `answer`: string
    - `citations`: array
    - `trace`: skill call list (optional)

Skill contract for this repository:

- `id`: stable skill id (`map_skill`, `path_retrieve_skill`, `vector_retrieve_skill`, `synthesis_skill`, `verify_skill`)
- `intent`: natural-language purpose boundary
- `input_schema`: JSON schema compatible with `ToolDesc.parameters`
- `output_schema`: normalized output (`text`, `citations`, `evidence`, `meta`)
- `risk_level`: `read_only | constrained_write | sensitive`
- `eval_binding`: metric set (`tool_call_accuracy`, `faithfulness`, `context_precision`, `context_recall`)

### Configuration Examples

```yaml
skill_rag:
  mode: hybrid
  runtime:
    execution_surface: frame_tool_orchestrator
    max_tool_rounds: 4
    timeout_seconds: 30
  router:
    strategy: deterministic_then_llm
    allow_parallel_calls: true
    budgets:
      max_tokens_per_turn: 12000
      max_skill_calls: 5
  skills:
    - id: map_skill
      enabled: true
      risk_level: read_only
    - id: path_retrieve_skill
      enabled: true
      risk_level: read_only
      sandbox_root: knowledge_base/
    - id: vector_retrieve_skill
      enabled: true
      risk_level: read_only
      top_k: 6
    - id: synthesis_skill
      enabled: true
      risk_level: read_only
    - id: verify_skill
      enabled: true
      risk_level: read_only
  evaluation:
    offline_gate:
      tool_call_accuracy_min: 0.80
      tool_call_f1_min: 0.75
      answer_faithfulness_min: 0.85
      context_precision_min: 0.70
      context_recall_min: 0.80
    online_monitor:
      p95_latency_ms_max: 4500
      cost_per_100_requests_max_usd: 25
      fallback_rate_max: 0.08
```

### Technical Requirements

- Do not fork runtime semantics: all skill execution must remain within existing frame orchestration model.
- Add typed skill metadata; list-only registry is insufficient for routing/governance/eval binding.
- Preserve `/api/v1` and stream frame backward compatibility.
- Ensure backend receives full conversation history (not only latest turn) for retrieval quality.
- Implement deterministic policy baseline before LLM router to control cost and debuggability.
- Add trace observability per skill call: input hash, selected args, latency, token usage, status.
- Close contract drift: either implement `/api/v1/chat/stream/pause` or remove references consistently.
- Build dual-lane eval:
  - Offline gating in CI with fixed datasets.
  - Online sampled audits for drift/cost/latency.

## Recommended Approach

Adopt one path: **Frame-first Skill Runtime + DeepResearch Adapter + Hybrid Retrieval**, rolled out in six controlled phases.

Phase 0 (Contract & parity)
- Introduce skill contract + metadata registry in `frame` while keeping behavior equivalent to current tool flow.

Phase 1 (Skillization inside frame)
- Implement `map/path/synthesis` as first-class skill adapters over existing `BaseTool` contract.

Phase 2 (Hybrid retrieval)
- Add `vector_retrieve_skill` and deterministic router; keep path retrieval for precision-sensitive queries.

Phase 3 (Backend integration)
- Switch deepresearch backend frame mode from `tools=[]` to injectable skill toolset; add optional stream meta traces.

Phase 4 (Frontend adaptation)
- Send full conversation history; surface optional skill trace panel with graceful fallback.

Phase 5 (Evaluation + operations)
- Reuse `frame/evaluation` harness pattern for skill-rag datasets and enforce CI thresholds.

Why this is optimal for this repo:

- Maximizes reuse of existing orchestrator/tool/runtime assets.
- Minimizes blast radius by avoiding parallel runtime implementation.
- Enables measurable progress per phase with hard gates (quality, latency, cost).

## Implementation Guidance

- **Objectives**: Land Skill-RAG in current repository with minimal rewrite, measurable quality uplift, and controlled operational risk.
- **Key Tasks**: Add skill metadata registry, implement retrieval/synthesis skills, wire backend tool injection, upgrade frontend history+trace handling, add eval datasets and gates.
- **Dependencies**: Existing frame orchestrator/tool contracts, deepresearch stream protocol, optional vector store backend, evaluator model access for LLM-judge metrics.
- **Success Criteria**: Compared to current baseline, multi-hop/negation query correctness improves; tool-call accuracy and faithfulness pass thresholds; p95 latency/cost remain within configured budget; streaming contract stays backward compatible.