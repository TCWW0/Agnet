from frame.core.message import LLMResponseFunCallMsg, ToolResponseMessage


def test_function_call_msg_from_raw() -> None:
    msg = LLMResponseFunCallMsg.from_raw(
        tool_name="calculater",
        call_id="call_1",
        arguments_json='{"operand1": "3", "operand2": "4", "operator": "+"}',
    )
    assert msg.role == "assistant"
    assert msg.type == "function"
    assert msg.tool_name == "calculater"
    assert msg.call_id == "call_1"
    assert msg.arguments["operand1"] == "3"


def test_tool_response_msg_from_tool_result() -> None:
    msg = ToolResponseMessage.from_tool_result(
        tool_name="calculater",
        call_id="call_1",
        status="success",
        output="3 + 4 的结果为 7",
    )
    assert msg.role == "tool"
    assert msg.type == "tool_response"
    assert msg.status == "success"
    assert msg.content.endswith("7")


def run() -> None:
    test_function_call_msg_from_raw()
    test_tool_response_msg_from_tool_result()
    print("OK")


if __name__ == "__main__":
    run()
