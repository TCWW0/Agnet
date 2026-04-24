from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from frame.tool.builtin.run_command import RunCommandTool


def test_run_command_supports_structured_command_and_args(tmp_path) -> None:
    tool = RunCommandTool(str(tmp_path))

    result = tool.execute({"command": "git", "args": "--version", "timeout_sec": 10})

    assert result.status == "success"
    assert "git version" in result.output.lower()
    details = result.details or {}
    assert details.get("command_base") == "git"


def test_run_command_rejects_legacy_cmd_field(tmp_path) -> None:
    tool = RunCommandTool(str(tmp_path))

    result = tool.execute({"cmd": "git --version"})

    assert result.status == "error"
    assert "missing 'command'" in result.output.lower()


def test_run_command_rejects_interactive_python(tmp_path) -> None:
    tool = RunCommandTool(str(tmp_path))

    result = tool.execute({"command": "python"})

    assert result.status == "error"
    assert "interactive python is not allowed" in result.output.lower()


def test_run_command_requires_command_input(tmp_path) -> None:
    tool = RunCommandTool(str(tmp_path))

    result = tool.execute({"timeout_sec": 5})

    assert result.status == "error"
    assert "missing 'command'" in result.output.lower()


def test_run_command_rejects_non_allowlisted_command(tmp_path) -> None:
    tool = RunCommandTool(str(tmp_path))

    result = tool.execute({"command": "bash", "args": "-lc 'echo hi'"})

    assert result.status == "error"
    assert "command not allowed" in result.output.lower()
