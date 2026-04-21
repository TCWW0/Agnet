from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Protocol, Sequence

from frame.evaluation.grader import grade_trial, is_trial_success
from frame.evaluation.models import EvalArmConfig, EvalCase, EvalConfig, EvalReport, TrialObservation, TrialResult
from frame.evaluation.report import build_eval_report

# 接受输入用例、评测配置，运行评测并返回评测报告
class EvalExecutor(Protocol):
    def run_trial(self, case: EvalCase, arm: EvalArmConfig, trial_index: int) -> TrialObservation:
        ...


def evaluate_dataset(
    *,
    cases: Sequence[EvalCase],
    config: EvalConfig,
    executor: EvalExecutor,
    eval_id: str | None = None,
    git_sha: str = "",
    model_name: str = "",
    harness_version: str = "0.1.0",
) -> EvalReport:
    if not cases:
        raise ValueError("No evaluation cases provided")

    resolved_eval_id = eval_id or f"{config.name}-{uuid.uuid4().hex[:8]}"
    trial_results: list[TrialResult] = []

    # 对于每个测试用例，将其在每个臂上(config.arms)运行多次(config.trials_per_case)获取结果
    # 在多臂上运行是为了来获取不同workload的表现差异，来验证memory hooks和memory tools的效果
    # 运行多次是为了来获取稳定的评测结果，减少偶然因素的影响
    for case in cases:
        for arm in config.arms:
            for offset in range(config.trials_per_case):
                trial_index = offset + 1    # 当前轮数，从1开始计数
                started = time.perf_counter()
                try:
                    observation = executor.run_trial(case=case, arm=arm, trial_index=trial_index)
                except Exception as exc:
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    trial_results.append(
                        TrialResult(
                            case_id=case.case_id,
                            suite=case.suite,
                            arm=arm.id,
                            trial_index=trial_index,
                            success=False,
                            grader_score_det=0.0,
                            grader_score_llm=0.0,
                            grader_score_final=0.0,
                            recall_at_1=0.0,
                            recall_at_3=0.0,
                            precision_at_3=0.0,
                            memory_usage_score=0.0,
                            conflict_sensitivity=0.0,
                            n_turns=1,
                            n_toolcalls=0,
                            total_tokens=0,
                            latency_ms=elapsed_ms,
                            answer_text=str(exc),
                            recalled_contents=[],
                            fail_reason="harness_error",
                        )
                    )
                    continue

                elapsed_ms = (time.perf_counter() - started) * 1000.0
                if observation.latency_ms <= 0.0:
                    observation = observation.model_copy(update={"latency_ms": elapsed_ms})

                score = grade_trial(case, observation)
                success = is_trial_success(case, score)
                trial_results.append(
                    TrialResult(
                        case_id=case.case_id,
                        suite=case.suite,
                        arm=arm.id,
                        trial_index=trial_index,
                        success=success,
                        grader_score_det=score.grader_score_det,
                        grader_score_llm=score.grader_score_llm,
                        grader_score_final=score.grader_score_final,
                        recall_at_1=score.recall_at_1,
                        recall_at_3=score.recall_at_3,
                        precision_at_3=score.precision_at_3,
                        memory_usage_score=score.memory_usage_score,
                        conflict_sensitivity=score.conflict_sensitivity,
                        n_turns=1,
                        n_toolcalls=observation.n_toolcalls,
                        total_tokens=observation.total_tokens,
                        latency_ms=observation.latency_ms,
                        answer_text=observation.answer_text,
                        recalled_contents=observation.recalled_contents,
                        fail_reason=score.fail_reason,
                    )
                )

    return build_eval_report(
        eval_id=resolved_eval_id,
        run_at=datetime.now(timezone.utc),
        config=config,
        trial_results=trial_results,
        git_sha=git_sha,
        model_name=model_name,
        harness_version=harness_version,
    )
