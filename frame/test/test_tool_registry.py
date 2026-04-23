from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frame.tool.builtin.calculater import CalculaterTool
from frame.tool.register import ToolRegistry


def test_tool_registry_executes_tool_and_returns_details() -> None:
    registry = ToolRegistry()
    registry.register_tool(CalculaterTool())

    result = registry.execute_tool(
        "calculater",
        {"operand1": "1", "operand2": "2", "operator": "+"},
    )

    assert result.status == "success"
    assert "结果为" in result.output


def test_tool_registry_returns_structured_error_for_missing_tool() -> None:
    registry = ToolRegistry()

    result = registry.execute_tool("missing_tool", {})

    assert result.status == "error"
    assert "not found" in result.output
