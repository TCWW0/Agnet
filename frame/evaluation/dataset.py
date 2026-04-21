from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import ValidationError

from frame.evaluation.models import EvalCase


def _extract_case_payload(raw_object: object, line_number: int) -> dict:
    if not isinstance(raw_object, dict):
        raise ValueError(f"Line {line_number}: each JSONL row must be an object")

    if "item" in raw_object:
        wrapped_item = raw_object.get("item")
        if not isinstance(wrapped_item, dict):
            raise ValueError(f"Line {line_number}: field 'item' must be an object")
        return wrapped_item

    return raw_object


def load_eval_cases(file_path: str) -> List[EvalCase]:
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Dataset path does not exist: {file_path}")

    cases: List[EvalCase] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw_line = line.strip()
            if not raw_line or raw_line.startswith("#"):
                continue

            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Line {line_number}: invalid JSON - {exc.msg}") from exc

            payload = _extract_case_payload(parsed, line_number)
            try:
                case = EvalCase.model_validate(payload)
            except ValidationError as exc:
                raise ValueError(f"Line {line_number}: invalid case schema - {exc}") from exc

            cases.append(case)

    if not cases:
        raise ValueError(f"No cases loaded from dataset: {file_path}")

    return cases
