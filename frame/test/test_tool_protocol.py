from frame.core.tool_protocol import ToolResult, normalize_tool_result
from frame.tool.calculator import Calculator


def test_toolresult_to_from_dict():
    tr = ToolResult(tool_name="Calculator", output=42, original_input="add 40 2")
    d = tr.to_dict()
    assert d["version"] == "1.0"
    assert d["tool_name"] == "Calculator"
    assert d["status"] == "ok"
    assert d["output"] == 42
    assert isinstance(d["timestamp"], str)
    tr2 = ToolResult.from_dict(d)
    assert tr2.tool_name == "Calculator"
    assert tr2.output == 42


def test_from_dict_missing_timestamp():
    raw = {"tool_name": "T", "output": 1}
    tr = ToolResult.from_dict(raw)
    assert isinstance(tr.timestamp, str)


def test_normalize_primitive():
    tr = normalize_tool_result(5, tool_name="Calculator", original_input="add 2 3")
    assert isinstance(tr, ToolResult)
    assert tr.output == 5
    assert tr.tool_name == "Calculator"
    assert tr.original_input == "add 2 3"
    assert tr.status == "ok"


def test_normalize_dict_with_version():
    raw = {"version": "1.0", "tool_name": "X", "status": "ok", "output": 123}
    tr = normalize_tool_result(raw)
    assert tr.tool_name == "X"
    assert tr.output == 123


def test_calculator_run_success():
    calc = Calculator()
    out = calc.run("add 3 5")
    assert isinstance(out, dict)
    assert out["status"] == "ok"
    assert out["output"] == 8
    assert out["original_input"] == "add 3 5"


def test_calculator_run_div_zero():
    calc = Calculator()
    out = calc.run("div 1 0")
    assert isinstance(out, dict)
    assert out["status"] == "error"
    assert "division by zero" in (out.get("error_message") or "")


def test_toolregistry_invoke_returns_json():
    from frame.tool.registry import ToolRegistry
    import json as _json

    reg = ToolRegistry()
    reg.register(Calculator())
    res = reg.invoke("Calculator", "add 4 6")
    assert isinstance(res, str)
    d = _json.loads(res)
    assert d["tool_name"] == "Calculator"
    assert d["status"] == "ok"
    assert d["output"] == 10
    assert d["original_input"] == "add 4 6"


def test_toolregistry_invoke_not_found():
    from frame.tool.registry import ToolRegistry
    import pytest

    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.invoke("NonExist", "x")
