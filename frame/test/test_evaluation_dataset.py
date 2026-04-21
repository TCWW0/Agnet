from __future__ import annotations

from pathlib import Path

import pytest

from frame.evaluation.dataset import load_eval_cases


def test_load_eval_cases_supports_wrapped_and_plain_rows(tmp_path: Path) -> None:
    dataset_file = tmp_path / "cases.jsonl"
    dataset_file.write_text(
        "\n".join(
            [
                '{"item":{"case_id":"c1","suite":"capability","session_id":"s1","agent_route":"simple","user_input":"u1","expected_answer":"a1","expected_memory_snippets":[],"noise_snippets":[],"should_recall":false,"tags":[]}}',
                '{"case_id":"c2","suite":"regression","session_id":"s2","agent_route":"react","user_input":"u2","expected_answer":"a2","expected_memory_snippets":["m"],"noise_snippets":[],"should_recall":true,"tags":["t"]}',
            ]
        ),
        encoding="utf-8",
    )

    cases = load_eval_cases(str(dataset_file))

    assert len(cases) == 2
    assert cases[0].case_id == "c1"
    assert cases[1].case_id == "c2"
    assert cases[1].suite.value == "regression"


def test_load_eval_cases_raises_on_empty_dataset(tmp_path: Path) -> None:
    dataset_file = tmp_path / "empty.jsonl"
    dataset_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="No cases loaded"):
        load_eval_cases(str(dataset_file))
