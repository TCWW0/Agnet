<!-- markdownlint-disable-file -->

# Task Research Notes: Skill-RAG Feasibility, Value, and Evaluation System

## Research Executed

### File Analysis

- /root/rag/deep-rag/README.md
  - Declares explicit contrast: "Traditional RAG: Fragment documents ... Deep RAG: Preserve structure ... map + navigate."
- /root/rag/deep-rag/backend/main.py
  - Confirms dual orchestration (`function` and `react`) and iterative tool-result loops over SSE.
- /root/rag/deep-rag/backend/prompts.py
  - Confirms map-first prompting and explicit tool contract (`retrieve_files` with `file_paths` array).
- /root/rag/deep-rag/backend/knowledge_base.py
  - Confirms current retrieval is path-based file/directory/root reads rather than ANN vector retrieval.
- /root/rag/deep-rag/.copilot-tracking/research/20260421-skill-rag-architecture-research.md
  - Baseline architecture strengths/risks already identified; used here as prior evidence to avoid duplicated analysis.

### Code Search Results

- tool_calling_mode|retrieve_files|create_file_retrieval_tool|process_tool_calls
  - Matches in `backend/main.py`, `backend/prompts.py`, `backend/knowledge_base.py`, and `backend/config.py`; validates tool-centric orchestration as the current control plane.
- Knowledge Base File Summary|Traditional RAG|Active Navigation
  - Matches in `README.md`; validates explicit repository design intent to move beyond chunk-only retrieval.
- ToolCallAccuracy|ToolCallF1|AgentGoalAccuracy|Faithfulness|ContextualPrecisionMetric|ContextualRecallMetric
  - No local matches under `.copilot-tracking/research/**` before this update; confirms eval framework content had not yet been consolidated in-repo.

### External Research

- #githubRepo:"truera/trulens RAG Triad context relevance groundedness answer relevance"
  - TruLens documentation/code repeatedly frames RAG quality through the triad: context relevance, groundedness, answer relevance.
  - Demonstrates root-cause diagnostics mapped directly to retrieval and generation stages.
  - Includes practical examples adding feedback functions and guardrails to RAG/agent pipelines.
- #githubRepo:"confident-ai/deepeval RAG metrics contextual precision recall faithfulness tool use"
  - Confirms five core RAG metrics (answer relevancy, faithfulness, contextual relevancy, contextual precision, contextual recall).
  - Provides agentic metrics (goal accuracy, tool use, argument correctness, plan adherence/quality, step efficiency).
  - Shows dataset/test-case driven execution suitable for CI regression gates.
- #githubRepo:"vibrantlabsai/ragas agent metrics tool call accuracy tool call f1 agent goal accuracy"
  - Confirms modern collections API for `ToolCallAccuracy`, `ToolCallF1`, and `AgentGoalAccuracy`.
  - Shows strict-order vs flexible-order tool-call evaluation and F1-based softer evaluation.
  - Provides reference-based and reference-free goal accuracy variants for agent workflows.
- #fetch:https://developers.openai.com/api/docs/guides/tools-skills
  - Skills are versioned bundles (`SKILL.md` + files) with hosted/local execution modes.
  - Supports skill versioning, default/latest pointers, and curated skill references.
  - Security guidance stresses developer-level curation and approval gates for sensitive actions.
- #fetch:https://developers.openai.com/api/docs/guides/evals
  - Documents full eval lifecycle: define eval schema/criteria, upload dataset, run asynchronously, inspect per-criteria results and token usage.
  - Supports API-native automation for repeatable benchmarking and regression tracking.
- #fetch:https://developers.openai.com/api/docs/guides/evaluation-best-practices
  - Recommends eval-driven development, architecture-aware eval placement (single-turn/workflow/agent/multi-agent), and continuous evaluation.
  - Recommends combining metric-based, human, and LLM-as-judge evaluators.
- #fetch:https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/
  - Plugins/functions are first-class orchestration units with strong emphasis on semantic descriptions, parameter clarity, and controlled tool count.
  - Advises balancing function granularity vs orchestration overhead.
- #fetch:https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/using-data-retrieval-functions-for-rag
  - Provides semantic-vs-classic retrieval trade-offs and recommends hybrid use by query class.
  - Emphasizes security posture: user-token authorization and avoiding sensitive data duplication.
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
  - Defines context precision as ranking-relevance quality and provides formula/implementations.
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/
  - Defines context recall as missing-relevant-information rate and provides claim-based formulation.
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
  - Defines faithfulness as the fraction of response claims supported by retrieved context.
- #fetch:https://www.anthropic.com/engineering
  - Anthropic engineering blog emphasizes agent tool-use reliability, structured outputs, and evaluation loops
  - ReAct-style reasoning + tool calling is a common pattern in production agents
  - Highlights importance of iterative evaluation rather than one-shot correctness

### Project Conventions

- Standards referenced: Existing repository conventions in `backend/*.py`, `README.md`, and previous research notes; no additional style guides found.
- Instructions followed: `.github/instructions/` and `copilot/` directories do not exist in this repository; guidance derived from executable code and official docs above.

## Key Discoveries

### Project Structure

The current system is already half-way toward Skill-RAG:

- It has an explicit tool boundary (`retrieve_files`) and iterative model-tool loop.
- It has a global map (`Knowledge Base File Summary`) that functions like a planning memory.
- It lacks explicit multi-skill decomposition, typed skill registry, and skill-level quality gates.

This means migration risk is moderate rather than high: architecture primitives for Skill-RAG already exist.

### Implementation Patterns

Feasibility analysis relative to "chunk + vectorize + retrieve":

| Dimension | Traditional Chunk+Vector RAG | Skill-RAG |
| --- | --- | --- |
| Retrieval abstraction | Single retriever primitive (semantic similarity first) | Multiple capability skills (map navigation, exact path retrieval, semantic recall, synthesis, verifier) |
| Complex tasks (negation, multi-hop, cross-table logic) | Often needs heavy prompt patching and reranking | Better decomposition via specialized skills and explicit tool traces |
| Explainability | Retriever score + limited rationale | Skill call trace, arguments, and per-skill outputs are inspectable |
| Operational control | Mostly index/embedding tuning | Governance per skill (allow-list, budgets, approvals, role separation) |
| Failure localization | Hard to isolate whether failure is retrieval or reasoning | Easier to localize to routing, a specific skill, or synthesis layer |
| Latency/cost | Usually lower for simple QA | Can be higher if over-orchestrated; requires budget policies |
| Engineering complexity | Lower initial complexity | Higher initial complexity but better scaling for heterogeneous tasks |

Feasibility conclusion:

- Replacing everything with Skill-RAG is unnecessary and risky.
- Best path is Hybrid Skill-RAG: keep vector retrieval as one skill while adding map/path/verification skills.
- This preserves baseline recall while improving controllability and debuggability for hard queries.

### Complete Examples

```python
# Source-adapted from backend/main.py + external metric patterns (Ragas/DeepEval/OpenAI Evals)
# Hybrid Skill-RAG control loop with explicit quality hooks.

skills = {
    "map_skill": MapSkill(),                # reads file-summary map
    "path_retrieve_skill": PathRetrieve(),  # deterministic file/dir retrieval
    "vector_retrieve_skill": VectorSearch(),# semantic fallback/expansion
    "synthesis_skill": SynthesisWithCite(), # answer + citations
}

policy = SkillPolicy(
    max_skill_calls=4,
    allow_parallel=True,
    cost_budget_tokens=12000,
)

trace = []
state = init_state(user_query)

for step in range(policy.max_skill_calls):
    route = router.select(state, skills=list(skills.keys()))
    result = skills[route.skill_name].run(route.arguments)
    trace.append({"skill": route.skill_name, "args": route.arguments, "result": result})
    state = update_state(state, result)

    if is_sufficient(state):
        break

final_answer = skills["synthesis_skill"].run({"state": state, "trace": trace})

# Offline gates (example)
scores = {
    "retrieval_context_precision": eval_context_precision(trace),
    "retrieval_context_recall": eval_context_recall(trace),
    "answer_faithfulness": eval_faithfulness(final_answer, trace),
    "tool_call_accuracy": eval_tool_call_accuracy(trace),
    "goal_success": eval_goal_accuracy(final_answer),
}
assert scores["answer_faithfulness"] >= 0.85
```

### API and Schema Documentation

Skill contract (recommended):

- `skill_id`: stable identifier
- `intent`: natural-language purpose boundary
- `input_schema`: strict JSON schema
- `output_schema`: strict JSON schema
- `risk_level`: read_only | constrained_write | sensitive
- `budget_cost_hint`: expected latency/tokens
- `required_approvals`: boolean/policy
- `eval_metrics`: metric set per skill (for example, `ToolCallAccuracy` for tool-heavy skills)

Evaluation schema (recommended):

- Retrieval layer: context precision, context recall, context relevancy
- Grounding layer: faithfulness/groundedness
- Orchestration layer: tool call accuracy, tool call F1, agent goal accuracy
- Outcome layer: task success rate, user acceptance proxy, fallback rate
- Efficiency layer: p95 latency, tokens/request, cost/request

### Configuration Examples

```yaml
skill_rag:
  mode: hybrid
  router:
    strategy: intent_plus_budget
    max_skill_calls: 4
    allow_parallel_calls: true
  skills:
    - id: map_skill
      risk_level: read_only
      enabled: true
    - id: path_retrieve_skill
      risk_level: read_only
      enabled: true
    - id: vector_retrieve_skill
      risk_level: read_only
      enabled: true
    - id: synthesis_skill
      risk_level: read_only
      enabled: true
  eval:
    offline_gate:
      answer_faithfulness_min: 0.85
      context_precision_min: 0.70
      tool_call_accuracy_min: 0.80
    online_monitor:
      p95_latency_ms_max: 4500
      cost_per_100_requests_max_usd: 25
```

### Technical Requirements

- Skill decomposition boundaries must be explicit and non-overlapping.
- Keep vector retrieval as a skill, not as a hidden subsystem, so routing and eval remain unified.
- Introduce skill-level observability (input args, outputs, duration, token usage).
- Build two-tier eval:
  - Offline: golden-set + adversarial set + regression gating.
  - Online: drift, latency, cost, fallback rate, and sampled human review.
- Require security controls for skills:
  - read-only default, path sandboxing, sensitive-action approvals, and audit logs.
- Define go/no-go thresholds before production traffic ramp.

## Recommended Approach

Adopt one single path: Hybrid Skill-RAG with evaluation-first rollout.

Why this is the best option:

- It captures Skill-RAG's core value (composability, debuggability, policy control) without losing the proven recall benefits of vector retrieval.
- It aligns with this repo's existing map-first/tool-loop design, minimizing rewrite cost.
- It naturally supports a quantifiable quality system where each skill and each stage has measurable KPIs.

Rollout shape:

1. Phase 1: Wrap existing capabilities as explicit skills (map/path/synthesis) and keep behavior equivalent.
2. Phase 2: Add vector retrieval as `vector_retrieve_skill` plus router policies.
3. Phase 3: Add evaluation gates (faithfulness, context precision/recall, tool metrics) to CI and release checks.
4. Phase 4: Add online monitoring and periodic human calibration.

# Implementation Guidance

- **Objectives**: Prove that Skill-RAG improves hard-query quality and system controllability while maintaining acceptable latency/cost.
- **Key Tasks**: Skill contract design; router policy implementation; hybrid retrieval integration; metric pipeline setup; offline/online eval operations.
- **Dependencies**: Existing FastAPI tool loop, summary-map pipeline, optional vector store, evaluator LLM for LLM-as-judge metrics, CI pipeline.
- **Success Criteria**: Compared with current baseline, achieve higher grounded correctness on multi-hop/negation queries, maintain or improve success rate, and keep p95 latency/cost within defined budgets while passing regression gates.


## Application Scenario Adaptation — Practical guide for self-hosted Skill-RAG service

This section adapts the research findings into a concise, actionable playbook you can follow to implement a Skill‑RAG service from this repository. It focuses on minimal, safe steps that preserve existing behavior while enabling skillization, observability, and CI gating.

1) Quick start checklist
- Wrap existing retrieval and synthesis logic as explicit skills (`map_skill`, `path_retrieve_skill`, `vector_retrieve_skill`, `synthesis_skill`).
- Add a minimal `SkillRegistry` and a deterministic router that can be incrementally enhanced (intent match → budget-aware routing → LLM routing).
- Emit per-skill telemetry: input args, outputs, duration, token usage, and success/failure flags.
- Create an offline golden-set (5–50 queries) and adversarial-set for regression tests.
- Wire a lightweight evaluator step in CI that runs the golden-set and asserts thresholds (faithfulness, retrieval precision, tool-call accuracy).

2) Minimal skill contract (recommended)

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel

class SkillInput(BaseModel):
  query: str
  params: Optional[Dict[str, Any]] = None

class SkillOutput(BaseModel):
  text: Optional[str] = None
  citations: Optional[list] = []
  metadata: Optional[dict] = {}

class Skill(ABC):
  id: str
  intent: str
  input_schema: Type[BaseModel]
  output_schema: Type[BaseModel]

  @abstractmethod
  def run(self, inp: SkillInput) -> SkillOutput:
    raise NotImplementedError()

class SkillRegistry:
  def __init__(self):
    self._skills: Dict[str, Skill] = {}

  def register(self, skill: Skill):
    self._skills[skill.id] = skill

  def get(self, skill_id: str) -> Skill:
    return self._skills[skill_id]

  def list(self):
    return list(self._skills.values())
```

Notes: follow the repository's `python-project-design` rules — use `pydantic` for schemas, keep adapters (LLM response parsing) separated, and avoid runtime guessing.

3) Simple router (pseudocode)

```python
def route_query(query: str):
  if query_contains_path(query):
    return 'path_retrieve_skill', {'path': extract_path(query)}
  if is_complex(query):
    return 'vector_retrieve_skill', {'query': query}
  return 'map_skill', {'query': query}
```

4) Golden queries (examples)
- Q1: "2024 年第一季度华南区市场布局的关键几点是什么？" — expected: [Knowledge-Base/2024-Market-Layout/South-China-Region.md]
- Q2: "SW-1500 的电池供应商是谁，以及合作起始年份？" — expected: Product-Line-A 与 Supplier-Partnership-Records （multi-file evidence）
- Q3: "有没有文档表明 AE-Pro-Flagship 不支持主动降噪？请给出处或说明为什么没有。" — expected: returns contradictions or 'no evidence' with an explainable rationale
- Q4: "为 SW-2200 提供三点优化建议并按优先级排序（列出处）。" — synthesis + citations
- Q5: "列出供应商的银行账户信息" — expected: blocked by policy (sensitive action)

5) CI test template (concept)

Create a small script `eval_golden.py` that:
- loads `golden_set.json` (list of {query, expected_refs})
- runs each query through the Skill-RAG test harness (router + skills, in test mode)
- collects trace and final answer
- runs metric evaluators (context precision/recall, faithfulness, tool_call_accuracy)
- fails CI if any metric below defined thresholds

Minimal assertion example in `eval_golden.py`:

```python
assert scores['answer_faithfulness'] >= 0.85
assert scores['retrieval_context_precision'] >= 0.70
assert scores['tool_call_accuracy'] >= 0.80
```

Optionally include a GitHub Actions job that runs `python eval_golden.py` and blocks merges on failures.

6) Deployment & security checklist
- Default to read-only skills; require explicit approvals for any skill with `risk_level: sensitive`.
- Enforce path normalization and sandboxing in `path_retrieve_skill` (deny access outside knowledge base root).
- Limit skill token budgets and add cost counters; fail fast on budget breaches.
- Add audit logging for all skill calls (who, when, args, outputs, duration).
- Run skills in isolated workers or containers with strict network egress policies for sensitive skills.

7) Phase milestones (delivery-friendly)
- Phase 0 (Prep): Define skill contract, create `SkillRegistry`, add telemetry hooks. Gate: registry + 3 wrapped skills + smoke tests.
- Phase 1 (Skillize): Wrap `map_skill`, `path_retrieve_skill`, `synthesis_skill`. Gate: parity tests (answers equal or better on 50-sample baseline).
- Phase 2 (Hybrid): Add `vector_retrieve_skill` + router policies. Gate: golden-set pass + CI thresholds.
- Phase 3 (Ops): Integrate CI evaluator, online monitors, sampled human review cadence. Gate: stable 2-week run with no regression and acceptable cost.

8) Next steps I can help with
- Scaffold starter files: `skill_base.py`, `skill_registry.py`, `router.py`, `eval_golden.py` and `golden_set.json`.
- Generate the 5–10 golden queries with expected reference file paths from your Knowledge-Base.
- Scaffold a GitHub Actions CI job that runs `eval_golden.py` and reports metrics.

If you want, I can now scaffold the minimal code and the `golden_set.json` for you. Which part should I create first?
