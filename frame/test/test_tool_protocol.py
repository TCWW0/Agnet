from frame.core.tool_protocol import ToolResult, normalize_tool_result
from frame.tool.calculator import Calculator
from frame.core.message import ToolMessage


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


def test_toolresult_to_from_json():
    tr = ToolResult(tool_name="Calculator", output=7, original_input={"operation": "add", "operand1": 3, "operand2": 4})
    payload = tr.to_json(ensure_ascii=False)
    tr2 = ToolResult.from_json(payload)
    assert tr2.tool_name == "Calculator"
    assert tr2.output == 7
    assert tr2.original_input["operation"] == "add"


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
    tool_msg = ToolMessage(tool_name="Calculator", tool_input={"operation": "add", "operand1": 3, "operand2": 5}, phase="call")
    out = calc.run(tool_msg)
    assert isinstance(out, ToolResult)
    assert out.status == "ok"
    assert out.output == 8
    assert out.original_input == tool_msg.tool_input


def test_calculator_run_div_zero():
    calc = Calculator()
    tool_msg = ToolMessage(tool_name="Calculator", tool_input={"operation": "div", "operand1": 1, "operand2": 0}, phase="call")
    out = calc.run(tool_msg)
    assert isinstance(out, ToolResult)
    assert out.status == "error"
    assert "division by zero" in (out.error_message or "")


def test_toolregistry_invoke_returns_json():
    from frame.tool.registry import ToolRegistry

    reg = ToolRegistry()
    reg.register(Calculator())
    tool_msg = ToolMessage(tool_name="Calculator", tool_input={"operation": "add", "operand1": 4, "operand2": 6}, phase="call")
    res = reg.invoke("Calculator", tool_msg)
    assert isinstance(res, ToolResult)
    assert res.tool_name == "Calculator"
    assert res.status == "ok"
    assert res.output == 10
    assert res.original_input == tool_msg.tool_input

    res_json = reg.invoke_json("Calculator", tool_msg)
    d = ToolResult.from_json(res_json)
    assert d.output == 10


def test_toolregistry_invoke_not_found():
    from frame.tool.registry import ToolRegistry
    import pytest

    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.invoke("NonExist", ToolMessage(tool_name="NonExist", tool_input={}, phase="call"))
