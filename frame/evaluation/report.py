from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

from frame.evaluation.metrics import mean, pass_at_k, pass_hat_k, safe_divide
from frame.evaluation.models import (
    ArmSuiteSummary,
    CaseAggregate,
    EvalArmId,
    EvalConfig,
    EvalReport,
    EvalSuite,
    SuiteDelta,
    TrialResult,
)


def _sort_key_suite_arm(suite: EvalSuite, arm: EvalArmId) -> Tuple[str, str]:
    return (suite.value, arm.value)


def build_case_aggregates(trial_results: List[TrialResult], pass_k: int) -> List[CaseAggregate]:
    grouped: Dict[Tuple[str, str, str], List[TrialResult]] = defaultdict(list)
    for result in trial_results:
        grouped[(result.case_id, result.suite.value, result.arm.value)].append(result)

    aggregates: List[CaseAggregate] = []
    for (case_id, suite_name, arm_name), records in grouped.items():
        ordered_records = sorted(records, key=lambda item: item.trial_index)
        successes = [record.success for record in ordered_records]

        aggregates.append(
            CaseAggregate(
                case_id=case_id,
                suite=EvalSuite(suite_name),
                arm=EvalArmId(arm_name),
                trial_count=len(ordered_records),
                success_rate=mean(1.0 if item else 0.0 for item in successes),
                pass_at_1=pass_at_k(successes, k=1),
                pass_at_k=pass_at_k(successes, k=pass_k),
                pass_hat_k=pass_hat_k(successes, k=pass_k),
            )
        )

    return sorted(aggregates, key=lambda item: (item.suite.value, item.arm.value, item.case_id))


def build_arm_suite_summaries(
    case_aggregates: List[CaseAggregate],
    trial_results: List[TrialResult],
) -> List[ArmSuiteSummary]:
    cases_by_key: Dict[Tuple[str, str], List[CaseAggregate]] = defaultdict(list)
    trials_by_key: Dict[Tuple[str, str], List[TrialResult]] = defaultdict(list)

    for aggregate in case_aggregates:
        cases_by_key[(aggregate.suite.value, aggregate.arm.value)].append(aggregate)

    for result in trial_results:
        trials_by_key[(result.suite.value, result.arm.value)].append(result)

    summaries: List[ArmSuiteSummary] = []
    keys = sorted(set(cases_by_key.keys()) | set(trials_by_key.keys()))
    for suite_name, arm_name in keys:
        suite = EvalSuite(suite_name)
        arm = EvalArmId(arm_name)
        case_items = cases_by_key.get((suite_name, arm_name), [])
        trial_items = trials_by_key.get((suite_name, arm_name), [])

        summaries.append(
            ArmSuiteSummary(
                suite=suite,
                arm=arm,
                case_count=len(case_items),
                trial_count=len(trial_items),
                success_rate=mean(1.0 if item.success else 0.0 for item in trial_items),
                pass_at_1=mean(item.pass_at_1 for item in case_items),
                pass_at_k=mean(item.pass_at_k for item in case_items),
                pass_hat_k=mean(item.pass_hat_k for item in case_items),
                mean_recall_at_1=mean(item.recall_at_1 for item in trial_items),
                mean_recall_at_3=mean(item.recall_at_3 for item in trial_items),
                mean_precision_at_3=mean(item.precision_at_3 for item in trial_items),
                mean_memory_usage_score=mean(item.memory_usage_score for item in trial_items),
                mean_conflict_sensitivity=mean(item.conflict_sensitivity for item in trial_items),
                mean_latency_ms=mean(item.latency_ms for item in trial_items),
                mean_total_tokens=mean(float(item.total_tokens) for item in trial_items),
                mean_n_toolcalls=mean(float(item.n_toolcalls) for item in trial_items),
            )
        )

    return sorted(summaries, key=lambda item: _sort_key_suite_arm(item.suite, item.arm))


def _empty_summary(suite: EvalSuite, arm: EvalArmId) -> ArmSuiteSummary:
    return ArmSuiteSummary(
        suite=suite,
        arm=arm,
        case_count=0,
        trial_count=0,
        success_rate=0.0,
        pass_at_1=0.0,
        pass_at_k=0.0,
        pass_hat_k=0.0,
        mean_recall_at_1=0.0,
        mean_recall_at_3=0.0,
        mean_precision_at_3=0.0,
        mean_memory_usage_score=0.0,
        mean_conflict_sensitivity=0.0,
        mean_latency_ms=0.0,
        mean_total_tokens=0.0,
        mean_n_toolcalls=0.0,
    )


def build_suite_deltas(arm_suite_summaries: List[ArmSuiteSummary]) -> List[SuiteDelta]:
    by_suite: Dict[EvalSuite, Dict[EvalArmId, ArmSuiteSummary]] = defaultdict(dict)
    for summary in arm_suite_summaries:
        by_suite[summary.suite][summary.arm] = summary

    deltas: List[SuiteDelta] = []
    for suite in sorted(by_suite.keys(), key=lambda item: item.value):
        arm_map = by_suite[suite]
        a_summary = arm_map.get(EvalArmId.A, _empty_summary(suite, EvalArmId.A))
        b_summary = arm_map.get(EvalArmId.B, _empty_summary(suite, EvalArmId.B))
        c_summary = arm_map.get(EvalArmId.C, _empty_summary(suite, EvalArmId.C))

        deltas.append(
            SuiteDelta(
                suite=suite,
                delta_success_b_vs_a=b_summary.success_rate - a_summary.success_rate,
                delta_success_c_vs_b=c_summary.success_rate - b_summary.success_rate,
                latency_ratio_b_vs_a=safe_divide(b_summary.mean_latency_ms, a_summary.mean_latency_ms),
                token_ratio_b_vs_a=safe_divide(b_summary.mean_total_tokens, a_summary.mean_total_tokens),
            )
        )

    return deltas


def build_eval_report(
    *,
    eval_id: str,
    run_at: datetime,
    config: EvalConfig,
    trial_results: List[TrialResult],
    git_sha: str,
    model_name: str,
    harness_version: str,
) -> EvalReport:
    resolved_k = min(config.pass_k, config.trials_per_case)
    case_aggregates = build_case_aggregates(trial_results, pass_k=resolved_k)
    arm_suite_summaries = build_arm_suite_summaries(case_aggregates, trial_results)
    suite_deltas = build_suite_deltas(arm_suite_summaries)

    return EvalReport(
        eval_id=eval_id,
        run_at=run_at,
        git_sha=git_sha,
        model_name=model_name,
        harness_version=harness_version,
        config_snapshot=config,
        trial_results=sorted(
            trial_results,
            key=lambda item: (item.suite.value, item.arm.value, item.case_id, item.trial_index),
        ),
        case_aggregates=case_aggregates,
        arm_suite_summaries=arm_suite_summaries,
        suite_deltas=suite_deltas,
    )
