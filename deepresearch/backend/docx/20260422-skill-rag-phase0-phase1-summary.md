<!-- markdownlint-disable-file -->

# Skill-RAG Phase 0-1 Summary (DeepResearch Backend)

Date: 2026-04-22

## Completed

1. Added a new deterministic Skill-RAG runtime under `deepresearch/backend/src/skill_rag`:
   - Skill contract and models
   - Skill registry
   - Deterministic router
   - Skills: `map_skill`, `path_retrieve_skill`, `vector_retrieve_skill`
   - Skill orchestrator and chat engine
2. Integrated `skill_rag` mode into backend config and engine factory.
3. Added best-effort pause route implementation:
   - `POST /api/v1/chat/stream/pause`
   - Pause state is respected during stream generation.
4. Added optional stream `meta` frame support to carry skill trace data.
5. Updated backend README for new mode/env configuration.
6. Added tests:
   - API pause route test
   - Skill-RAG engine tests (summary/chunk/path retrieval)
7. Frontend request strategy upgraded to send full conversation history to backend (instead of only latest user message).

## Validation

Executed:
- `/root/agent/.venv/bin/python -m pytest deepresearch/backend/tests -q`

Result:
- `9 passed, 1 skipped`

## Not Completed Yet

1. Frontend skill trace visualization panel (consume and render stream `meta.skillTrace`).
2. Offline eval dataset + CI gate (faithfulness/context precision/tool call metrics).
3. Hybrid synthesis with optional LLM summarizer and strict citation enforcement.
4. Cost/latency budget guardrail instrumentation for each skill call.

## Risks

1. Current vector retrieval is deterministic lexical matching, not embedding-based ANN retrieval.
2. Skill router is deterministic-only in this phase; complex intent routing quality is limited.
3. No persistent conversation store in backend yet; history is passed from frontend per request.

## Next Step Recommendation

Phase 2 candidate tasks:
1. Add embedding-backed retriever as `vector_retrieve_skill` backend option, keep lexical fallback.
2. Introduce structured eval harness for golden/adversarial sets and CI thresholds.
3. Expose optional frontend trace inspector using stream `meta.skillTrace`.
