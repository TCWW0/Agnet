from frame.tool.todo import TODOTool
from frame.core.tool_protocol import ToolResult
from frame.core.message import ToolMessage
import dotenv
import os
dotenv.load_dotenv()

class TestTODOTool:
    def test_todo_add(self):
        # 需要清除之前测试可能产生的json持久化文件，确保测试环境干净
        persist_path = os.getenv("TODO_JSON_PATH")
        if persist_path:
            persist_path = os.path.join(persist_path, "test_todo_add.json")
        else:
            persist_path = "test_todo_add.json"
        if os.path.exists(persist_path):
            os.remove(persist_path)
        todoTool = TODOTool(storage_path="test_todo_add.json")
        call_msg = ToolMessage(tool_name="TODO", tool_input={"op": "add", "content": "买菜"}, phase="call")
        result = todoTool.run(call_msg)
        assert isinstance(result, ToolResult)
        assert result.status == "ok"
        list_result = todoTool.run(ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"))
        # 只有一条待办事项，且内容正确,且list指令会将各个事项塞进Output列表中
        assert len(list_result.output) == 1
        assert list_result.output[0]["content"] == "买菜"
        assert list_result.output[0]["status"] == "PENDING"

    def test_todo_batch_add(self):
        persist_path = os.getenv("TODO_JSON_PATH")
        if persist_path:
            persist_path = os.path.join(persist_path, "test_todo_batch_add.json")
        else:
            persist_path = "test_todo_batch_add.json"
        if os.path.exists(persist_path):
            os.remove(persist_path)

        todoTool = TODOTool(storage_path="test_todo_batch_add.json")
        call_msg = ToolMessage(
            tool_name="TODO",
            tool_input={
                "ops": [
                    {"op": "add", "content": "任务A"},
                    {"op": "add", "content": "任务B"},
                    {"op": "add", "content": "任务C"},
                ]
            },
            phase="call",
        )
        result = todoTool.run(call_msg)
        assert isinstance(result, ToolResult)
        assert result.status == "ok"
        assert isinstance(result.output, dict)
        assert result.output.get("batch") is True
        assert result.output.get("total") == 3
        assert result.output.get("ok_count") == 3

        list_result = todoTool.run(ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"))
        assert isinstance(list_result.output, list)
        assert len(list_result.output) == 3
        