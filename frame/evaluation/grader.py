from __future__ import annotations

import re

from frame.evaluation.metrics import precision_at_k, recall_at_k
from frame.evaluation.models import EvalCase, TrialObservation, TrialScore


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _snippet_hits(snippets: list[str], text: str) -> int:
    if not snippets:
        return 0

    normalized_text = _normalize_text(text)
    hits = 0
    for snippet in snippets:
        if _normalize_text(snippet) and _normalize_text(snippet) in normalized_text:
            hits += 1
    return hits


def _answer_matches(case: EvalCase, answer_text: str) -> bool:
    expected = case.expected_answer

    if case.answer_match_mode.value == "exact":
        return _normalize_text(answer_text) == _normalize_text(expected)

    if case.answer_match_mode.value == "regex":
        try:
            return re.search(expected, answer_text, flags=re.IGNORECASE) is not None
        except re.error:
            # Fallback to a stable contains check if regex is malformed.
            return _normalize_text(expected) in _normalize_text(answer_text)

    return _normalize_text(expected) in _normalize_text(answer_text)


def _memory_usage_score(case: EvalCase, answer_text: str) -> float:
    if not case.expected_memory_snippets:
        return 1.0

    hits = _snippet_hits(case.expected_memory_snippets, answer_text)
    return hits / len(case.expected_memory_snippets)


def _conflict_sensitivity(case: EvalCase, answer_text: str) -> float:
    if not case.noise_snippets:
        return 1.0

    conflict_hits = _snippet_hits(case.noise_snippets, answer_text)
    if conflict_hits == 0:
        return 1.0
    return 0.0


def grade_trial(case: EvalCase, observation: TrialObservation) -> TrialScore:
    rule_correctness = 1.0 if _answer_matches(case, observation.answer_text) else 0.0
    recall_1 = recall_at_k(case.expected_memory_snippets, observation.recalled_contents, k=1)
    recall_3 = recall_at_k(case.expected_memory_snippets, observation.recalled_contents, k=3)
    precision_3 = precision_at_k(case.expected_memory_snippets, observation.recalled_contents, k=3)
    usage_score = _memory_usage_score(case, observation.answer_text)
    conflict_score = _conflict_sensitivity(case, observation.answer_text)

    if case.should_recall:
        det_score = (0.55 * rule_correctness) + (0.20 * recall_3) + (0.15 * precision_3) + (0.10 * usage_score)
    else:
        det_score = (0.80 * rule_correctness) + (0.20 * conflict_score)

    det_score *= conflict_score

    fail_reason = None
    if rule_correctness < 1.0:
        fail_reason = "judge_fail"
    elif case.should_recall and recall_3 <= 0.0:
        fail_reason = "retrieval_miss"
    elif conflict_score < 1.0:
        fail_reason = "use_error"

    return TrialScore(
        rule_correctness=rule_correctness,
        grader_score_det=det_score,
        grader_score_llm=0.0,
        grader_score_final=det_score,
        recall_at_1=recall_1,
        recall_at_3=recall_3,
        precision_at_3=precision_3,
        memory_usage_score=usage_score,
        conflict_sensitivity=conflict_score,
        fail_reason=fail_reason,
    )


def is_trial_success(case: EvalCase, score: TrialScore) -> bool:
    if case.should_recall:
        return score.rule_correctness >= 1.0 and score.recall_at_3 > 0.0 and score.conflict_sensitivity >= 1.0

    return score.rule_correctness >= 1.0 and score.conflict_sensitivity >= 1.0
