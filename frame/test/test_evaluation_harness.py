from __future__ import annotations

from frame.evaluation.harness import evaluate_dataset
from frame.evaluation.models import EvalArmId, EvalCase, EvalConfig, EvalSuite, TrialObservation


class _FakeExecutor:
    def run_trial(self, case: EvalCase, arm, trial_index: int) -> TrialObservation:
        if case.case_id == "cap_case":
            if arm.id == EvalArmId.A:
                return TrialObservation(
                    answer_text="i do not know",
                    recalled_contents=[],
                    total_tokens=12,
                    n_toolcalls=0,
                )

            tool_calls = 1 if arm.id == EvalArmId.C else 0
            tokens = 18 if arm.id == EvalArmId.B else 22
            return TrialObservation(
                answer_text=case.expected_answer,
                recalled_contents=["my name is alice"],
                total_tokens=tokens,
                n_toolcalls=tool_calls,
            )

        return TrialObservation(
            answer_text=case.expected_answer,
            recalled_contents=[],
            total_tokens=10,
            n_toolcalls=0,
        )


def test_evaluate_dataset_builds_arm_level_deltas_and_pass_metrics() -> None:
    cases = [
        EvalCase(
            case_id="cap_case",
            suite=EvalSuite.CAPABILITY,
            session_id="s_cap",
            agent_route="simple",
            user_input="what is my name",
            expected_answer="your name is alice",
            expected_memory_snippets=["my name is alice"],
            noise_snippets=[],
            should_recall=True,
            tags=["capability"],
        ),
        EvalCase(
            case_id="reg_case",
            suite=EvalSuite.REGRESSION,
            session_id="s_reg",
            agent_route="simple",
            user_input="2+3",
            expected_answer="5",
            expected_memory_snippets=[],
            noise_snippets=[],
            should_recall=False,
            tags=["regression"],
        ),
    ]
    config = EvalConfig(name="unit-eval", dataset_path="unused", trials_per_case=3, pass_k=3)

    report = evaluate_dataset(cases=cases, config=config, executor=_FakeExecutor())

    # 长度 = len(cases) * len(config.arms) * config.trials_per_case = 2 * 3 * 3 = 18
    assert len(report.trial_results) == 18

    cap_a = next(
        summary
        for summary in report.arm_suite_summaries
        if summary.suite.value == "capability" and summary.arm.value == "A"
    )
    cap_b = next(
        summary
        for summary in report.arm_suite_summaries
        if summary.suite.value == "capability" and summary.arm.value == "B"
    )
    assert cap_a.success_rate == 0.0
    assert cap_b.success_rate == 1.0
    assert cap_b.pass_hat_k == 1.0

    capability_delta = next(delta for delta in report.suite_deltas if delta.suite.value == "capability")
    assert capability_delta.delta_success_b_vs_a > 0.9
