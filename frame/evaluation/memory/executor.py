from __future__ import annotations

from typing import List

from frame.evaluation.models import EvalCase, EvalArmConfig, TrialObservation
from frame.memory.base import InMemoryMemoryKernel, AgentMemoryHooks, MemoryToolFacade, SessionRef


class MemoryKernelEvalExecutor:
    """A simple EvalExecutor that exercises an InMemoryMemoryKernel.

    Behavior:
    - If `arm.memory_hooks` is True, use `AgentMemoryHooks.before_invoke` to collect recalled messages.
    - If `arm.memory_tools` is True, call `MemoryToolFacade.recall` to simulate tool-driven recalls (counts as a toolcall).
    - Compose recalled_contents and produce an answer_text:
      - For `should_recall` cases: if expected snippet is present in recalled_contents -> return the expected_answer.
        if a noise snippet is present -> produce a conflicted answer including the noise (to trigger conflict sensitivity).
      - For non-recall cases: return the expected_answer (simulate correct computation).

    若arm.memory_hooks为真，此时会使用AgentMemoryHooks.before_invoke来收集被检索到的消息；
    如果arm.memory_tools为真，则调用MemoryToolFacade.recall来模拟工具驱动的回忆（这会计为一次工具调用）。
    然后根据recalled_contents来生成answer_text：对于should_recall为真的用例，
        如果expected snippet出现在recalled_contents中，则返回expected_answer；
        如果noise snippet出现在recalled_contents中，则生成一个包含noise的冲突答案（以触发冲突敏感度）。
        对于非should_recall用例，直接返回expected_answer（模拟正确的计算结果）。
    """

    def __init__(self, kernel: InMemoryMemoryKernel) -> None:
        self.kernel = kernel
        self.facade = MemoryToolFacade(kernel)      # 在每次问答直接的规则式固定检索
        self.hooks = AgentMemoryHooks(kernel)       # 模拟Agent在执行时调用工具的行为，触发hooks的检索逻辑

    def run_trial(self, case: EvalCase, arm: EvalArmConfig, trial_index: int) -> TrialObservation:
        session = SessionRef(session_id=case.session_id)

        recalled: List[str] = []

        if arm.memory_hooks:
            merged = self.hooks.before_invoke(session, case.user_input, [])
            recalled.extend([m.content for m in merged if getattr(m, "content", None)])

        if arm.memory_tools:
            tool_recalls = self.facade.recall(session, query=case.user_input, top_k=3)
            recalled.extend(tool_recalls)

        # 此时根据配置，使用对应的工具路径或hooks路径，获取到了本次执行时的检索结果，接下来进行打分
        # keep order and uniqueness
        seen = set()
        recalled_unique = []
        for item in recalled:
            key = (item or "").strip()
            if not key:
                continue
            lower = key.lower()
            if lower in seen:
                continue
            seen.add(lower)
            recalled_unique.append(key)

        # Decide answer_text based on recalled content
        answer_text = ""
        if case.should_recall:
            # conflict if any noise_snippet present
            noise_hit = None
            for noise in case.noise_snippets:
                for r in recalled_unique:
                    if noise.lower() in r.lower():
                        noise_hit = noise
                        break
                if noise_hit:
                    break

            if noise_hit:
                answer_text = f"conflicted: {noise_hit}"
            else:
                expected_hit = None
                for expect in case.expected_memory_snippets:
                    for r in recalled_unique:
                        if expect.lower() in r.lower():
                            expected_hit = expect
                            break
                    if expected_hit:
                        break

                if expected_hit:
                    answer_text = case.expected_answer
                else:
                    answer_text = "I don't know"
        else:
            # regression or computation-style case: answer directly
            answer_text = case.expected_answer

        total_tokens = max(1, len(answer_text.split()))
        n_toolcalls = 1 if arm.memory_tools else 0

        return TrialObservation(
            answer_text=answer_text,
            recalled_contents=recalled_unique,
            latency_ms=0.0,
            total_tokens=total_tokens,
            n_toolcalls=n_toolcalls,
            trace={"executor": "MemoryKernelEvalExecutor", "trial_index": str(trial_index)},
        )
