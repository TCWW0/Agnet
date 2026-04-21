from __future__ import annotations

import pytest

from frame.evaluation.metrics import pass_at_k, pass_hat_k, precision_at_k, recall_at_k


def test_pass_metrics_use_closed_form_probabilities() -> None:
    successes = [True, False, True]

    assert pass_at_k(successes, k=1) == pytest.approx(2 / 3)
    assert pass_at_k(successes, k=2) == pytest.approx(1.0)
    assert pass_hat_k(successes, k=2) == pytest.approx(1 / 3)


def test_retrieval_metrics_basic_behavior() -> None:
    expected = ["alpha", "beta"]
    recalled = ["beta", "gamma", "alpha"]

    assert recall_at_k(expected, recalled, k=1) == pytest.approx(0.5)
    assert recall_at_k(expected, recalled, k=3) == pytest.approx(1.0)

    assert precision_at_k(expected, recalled, k=1) == pytest.approx(1.0)
    assert precision_at_k(expected, recalled, k=3) == pytest.approx(2 / 3)
