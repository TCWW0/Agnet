import json

from frame.agent.process_agent import ProcessAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.message import ToolMessage
from frame.tool.todo import TODOTool


class FakeLLM(LLMClient):
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    def invoke(self, prompt: str) -> str:
        if self._idx >= len(self._responses):
            return "final 执行完成"
        out = self._responses[self._idx]
        self._idx += 1
        return out

def _list_items(todo_tool):
    tr = todo_tool.run(ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"))
    assert tr.status == "ok"
    assert isinstance(tr.output, list)
    return [it for it in tr.output if isinstance(it, dict)]


def _build_agent(monkeypatch, tmp_path, responses, file_name="process_agent_test.json"):
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    todo = TODOTool(storage_path=file_name)
    agent = ProcessAgent(
        name="process_agent_test",
        config=AgentConfig(max_rounds=6),
        llm=FakeLLM(responses),
        todo_tool=todo,
    )
    return agent, todo


def test_process_agent_executes_one_pending_item(monkeypatch, tmp_path):
    agent, todo = _build_agent(
        monkeypatch,
        tmp_path,
        [
            "think 先分析任务范围",
            "final 已完成任务A：给出执行产物",
        ],
    )

    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务A",
                "metadata": {"plan_id": "p1", "objective": "总体目标", "order": 1},
            },
            phase="call",
        )
    )
    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务B",
                "metadata": {"plan_id": "p1", "objective": "总体目标", "order": 2},
            },
            phase="call",
        )
    )

    ret = agent.think(json.dumps({"objective": "总体目标", "plan_id": "p1"}, ensure_ascii=False))
    assert "已完成任务#1" in ret

    items = sorted(_list_items(todo), key=lambda x: int(x.get("id", 0)))
    assert items[0].get("status") == "COMPLETED"
    assert items[0].get("claimed_by") is None
    responses = items[0].get("responses") or []
    assert responses
    assert "已完成任务A" in str(responses[-1].get("content"))

    assert items[1].get("status") == "PENDING"


def test_process_agent_build_context_contains_plan_and_recent(monkeypatch, tmp_path):
    agent, todo = _build_agent(monkeypatch, tmp_path, ["final ok"], file_name="process_context_test.json")

    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务A",
                "metadata": {"plan_id": "p2", "objective": "做一个Demo", "order": 1},
            },
            phase="call",
        )
    )
    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务B",
                "metadata": {"plan_id": "p2", "objective": "做一个Demo", "order": 2},
            },
            phase="call",
        )
    )

    todo.run(ToolMessage(tool_name="TODO", tool_input={"op": "add_response", "id": 1, "response": "任务A已输出结果"}, phase="call"))
    todo.run(ToolMessage(tool_name="TODO", tool_input={"op": "update", "id": 1, "status": "COMPLETED"}, phase="call"))

    items = [it for it in _list_items(todo) if it.get("metadata", {}).get("plan_id") == "p2"]
    current = [it for it in items if int(it.get("id", 0)) == 2][0]

    context = agent.build_context("做一个Demo", items, current)
    assert "做一个Demo" == context["objective"]
    assert "#1 [COMPLETED] 任务A" in context["plan_summary"]
    assert "任务A已输出结果" in context["recent_results"]
    assert context["item_content"] == "任务B"


def test_process_agent_returns_no_pending_message(monkeypatch, tmp_path):
    agent, todo = _build_agent(monkeypatch, tmp_path, ["final ignored"], file_name="process_no_pending_test.json")

    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "已完成任务",
                "metadata": {"plan_id": "p3", "objective": "目标", "order": 1},
            },
            phase="call",
        )
    )
    todo.run(ToolMessage(tool_name="TODO", tool_input={"op": "update", "id": 1, "status": "COMPLETED"}, phase="call"))

    ret = agent.think(json.dumps({"objective": "目标", "plan_id": "p3"}, ensure_ascii=False))
    assert "没有待执行任务" in ret


def test_process_agent_fallback_when_no_final(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    todo = TODOTool(storage_path="process_fallback_test.json")

    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务X",
                "metadata": {"plan_id": "p4", "objective": "目标", "order": 1},
            },
            phase="call",
        )
    )

    # 连续 think，不给 final，触发兜底路径
    agent = ProcessAgent(
        name="process_agent_fallback",
        config=AgentConfig(max_rounds=3),
        llm=FakeLLM(["think 分析中", "think 分析中", "think 分析中"]),
        todo_tool=todo,
    )

    ret = agent.think(json.dumps({"objective": "目标", "plan_id": "p4"}, ensure_ascii=False))
    assert "执行未完成" in ret

    items = _list_items(todo)
    assert items[0].get("status") == "COMPLETED"
    responses = items[0].get("responses") or []
    assert responses
    assert "执行未完成" in str(responses[-1].get("content"))


def test_process_agent_supports_item_id_selection(monkeypatch, tmp_path):
    agent, todo = _build_agent(monkeypatch, tmp_path, ["final 已完成指定任务"], file_name="process_item_id_test.json")

    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务1",
                "metadata": {"plan_id": "p5", "objective": "目标", "order": 1},
            },
            phase="call",
        )
    )
    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": "任务2",
                "metadata": {"plan_id": "p5", "objective": "目标", "order": 2},
            },
            phase="call",
        )
    )

    ret = agent.think(json.dumps({"objective": "目标", "plan_id": "p5", "item_id": 2}, ensure_ascii=False))
    assert "已完成任务#2" in ret

    items = sorted(_list_items(todo), key=lambda x: int(x.get("id", 0)))
    assert items[0].get("status") == "PENDING"
    assert items[1].get("status") == "COMPLETED"
