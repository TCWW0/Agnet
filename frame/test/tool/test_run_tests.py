from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.run_tests import RunTestsTool


def test_run_tests_returns_structured_hint_when_pattern_missing(tmp_path) -> None:
    tool = RunTestsTool(workspace_root=str(tmp_path), pytest_cmd="/root/agent/.venv/bin/pytest -q")
    result = tool.execute({"pattern": "test_*.py"})

    assert result.status == "error"
    assert isinstance(result.details, dict)
    assert result.details.get("exit_code") == 4
    assert result.details.get("error_type") == "tests_not_found"
    assert "Create or point to an existing pytest file" in str(result.details.get("action_hint", ""))
