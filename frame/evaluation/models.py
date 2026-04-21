from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EvalSuite(str, Enum):
    CAPABILITY = "capability"
    REGRESSION = "regression"


class EvalArmId(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class AnswerMatchMode(str, Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"


FailReason = Literal["retrieval_miss", "use_error", "judge_fail", "harness_error"]

# 描述一个用例
class EvalCase(BaseModel):
    case_id: str = Field(min_length=1)
    suite: EvalSuite
    session_id: str = Field(min_length=1)
    agent_route: str = Field(default="simple", min_length=1)
    user_input: str = Field(min_length=1)
    expected_answer: str = Field(min_length=1)
    expected_memory_snippets: List[str] = Field(default_factory=list)
    noise_snippets: List[str] = Field(default_factory=list)
    should_recall: bool = True
    difficulty: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    answer_match_mode: AnswerMatchMode = AnswerMatchMode.CONTAINS

    model_config = ConfigDict(extra="forbid")


class EvalDatasetRow(BaseModel):
    item: EvalCase

    model_config = ConfigDict(extra="forbid")

# 一个Arm的配置，描述了评测中不同的实验条件，其实就是通过不同臂的对比来验证memory hooks和memory tools的效果
class EvalArmConfig(BaseModel):
    id: EvalArmId
    name: str = Field(min_length=1)
    memory_hooks: bool
    memory_tools: bool

    model_config = ConfigDict(extra="forbid")


class EvalThresholds(BaseModel):
    min_delta_success_b_vs_a: float = 0.08
    min_delta_judge_b_vs_a: float = 0.05
    min_pass_hat_k_regression: float = 0.90
    max_latency_ratio_b_vs_a: float = 1.35
    max_token_ratio_b_vs_a: float = 1.40

    model_config = ConfigDict(extra="forbid")


def default_eval_arms() -> List[EvalArmConfig]:
    return [
        EvalArmConfig(id=EvalArmId.A, name="no_memory", memory_hooks=False, memory_tools=False),
        EvalArmConfig(id=EvalArmId.B, name="forced_memory_only", memory_hooks=True, memory_tools=False),
        EvalArmConfig(id=EvalArmId.C, name="forced_plus_tools", memory_hooks=True, memory_tools=True),
    ]


class EvalConfig(BaseModel):
    name: str = Field(default="frame-memory-eval-v2", min_length=1)
    dataset_path: str = Field(min_length=1)
    random_seed: int = 42
    trials_per_case: int = Field(default=3, ge=1)
    pass_k: int = Field(default=3, ge=1)
    arms: List[EvalArmConfig] = Field(default_factory=default_eval_arms)
    thresholds: EvalThresholds = Field(default_factory=EvalThresholds)

    model_config = ConfigDict(extra="forbid")


class TrialObservation(BaseModel):
    answer_text: str = ""
    recalled_contents: List[str] = Field(default_factory=list)
    latency_ms: float = Field(default=0.0, ge=0.0)
    total_tokens: int = Field(default=0, ge=0)
    n_toolcalls: int = Field(default=0, ge=0)
    trace: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class TrialScore(BaseModel):
    rule_correctness: float = Field(ge=0.0, le=1.0)
    grader_score_det: float = Field(ge=0.0, le=1.0)
    grader_score_llm: float = Field(default=0.0, ge=0.0, le=1.0)
    grader_score_final: float = Field(ge=0.0, le=1.0)
    recall_at_1: float = Field(ge=0.0, le=1.0)
    recall_at_3: float = Field(ge=0.0, le=1.0)
    precision_at_3: float = Field(ge=0.0, le=1.0)
    memory_usage_score: float = Field(ge=0.0, le=1.0)
    conflict_sensitivity: float = Field(ge=0.0, le=1.0)
    fail_reason: Optional[FailReason] = None

    model_config = ConfigDict(extra="forbid")


class TrialResult(BaseModel):
    case_id: str
    suite: EvalSuite
    arm: EvalArmId
    trial_index: int = Field(ge=1)
    success: bool

    grader_score_det: float = Field(ge=0.0, le=1.0)
    grader_score_llm: float = Field(ge=0.0, le=1.0)
    grader_score_final: float = Field(ge=0.0, le=1.0)
    recall_at_1: float = Field(ge=0.0, le=1.0)
    recall_at_3: float = Field(ge=0.0, le=1.0)
    precision_at_3: float = Field(ge=0.0, le=1.0)
    memory_usage_score: float = Field(ge=0.0, le=1.0)
    conflict_sensitivity: float = Field(ge=0.0, le=1.0)

    n_turns: int = Field(default=1, ge=1)
    n_toolcalls: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)

    answer_text: str = ""
    recalled_contents: List[str] = Field(default_factory=list)
    fail_reason: Optional[FailReason] = None

    model_config = ConfigDict(extra="forbid")


class CaseAggregate(BaseModel):
    case_id: str
    suite: EvalSuite
    arm: EvalArmId
    trial_count: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    pass_at_1: float = Field(ge=0.0, le=1.0)
    pass_at_k: float = Field(ge=0.0, le=1.0)
    pass_hat_k: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ArmSuiteSummary(BaseModel):
    suite: EvalSuite
    arm: EvalArmId
    case_count: int = Field(ge=0)
    trial_count: int = Field(ge=0)
    success_rate: float = Field(ge=0.0, le=1.0)
    pass_at_1: float = Field(ge=0.0, le=1.0)
    pass_at_k: float = Field(ge=0.0, le=1.0)
    pass_hat_k: float = Field(ge=0.0, le=1.0)

    mean_recall_at_1: float = Field(ge=0.0, le=1.0)
    mean_recall_at_3: float = Field(ge=0.0, le=1.0)
    mean_precision_at_3: float = Field(ge=0.0, le=1.0)
    mean_memory_usage_score: float = Field(ge=0.0, le=1.0)
    mean_conflict_sensitivity: float = Field(ge=0.0, le=1.0)

    mean_latency_ms: float = Field(ge=0.0)
    mean_total_tokens: float = Field(ge=0.0)
    mean_n_toolcalls: float = Field(ge=0.0)

    model_config = ConfigDict(extra="forbid")


class SuiteDelta(BaseModel):
    suite: EvalSuite
    delta_success_b_vs_a: float
    delta_success_c_vs_b: float
    latency_ratio_b_vs_a: float
    token_ratio_b_vs_a: float

    model_config = ConfigDict(extra="forbid")


class EvalReport(BaseModel):
    eval_id: str
    run_at: datetime
    git_sha: str = ""
    model_name: str = ""
    harness_version: str = "0.1.0"

    config_snapshot: EvalConfig
    trial_results: List[TrialResult] = Field(default_factory=list)
    case_aggregates: List[CaseAggregate] = Field(default_factory=list)
    arm_suite_summaries: List[ArmSuiteSummary] = Field(default_factory=list)
    suite_deltas: List[SuiteDelta] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
