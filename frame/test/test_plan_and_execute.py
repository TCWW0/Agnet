import json

from frame.agent.plan_and_execute import PlanAndExecuteAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.message import ToolMessage


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


def _build_agent(monkeypatch, tmp_path, responses):
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    llm = FakeLLM(responses)
    return PlanAndExecuteAgent(
        name="plan_execute_test_agent",
        config=AgentConfig(max_rounds=8),
        llm=llm,
        todo_storage_path="plan_execute_test.json",
    )


def _list_created_items(agent):
    tr = agent.tool_registry.invoke(
        "TODO",
        ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"),
    )
    assert tr.status == "ok"
    assert isinstance(tr.output, list)
    items = [it for it in tr.output if isinstance(it, dict)]
    return [
        it
        for it in items
        if isinstance(it.get("metadata"), dict)
        and it["metadata"].get("source") == "plan_and_execute"
    ]


def test_plan_and_execute_full_flow(monkeypatch, tmp_path):
    responses = [
        json.dumps(["梳理需求", "设计执行步骤", "实现并自测"], ensure_ascii=False),
        "final 已完成梳理需求：输出需求清单",
        "final 已完成设计执行步骤：给出执行序列",
        "final 已完成实现并自测：完成基础验证",
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    final_text = agent.think("请实现一个最小可用的 plan-and-execute 流程")
    assert "共 3 项" in final_text
    assert "完成 3 项" in final_text

    items = sorted(_list_created_items(agent), key=lambda x: int(x.get("id", 0)))
    assert len(items) == 3
    for it in items:
        assert it.get("status") == "COMPLETED"
        assert it.get("claimed_by") is None
        assert isinstance(it.get("responses"), list)
        assert len(it.get("responses")) >= 1    # type: ignore


def test_plan_deduplicates_same_tasks(monkeypatch, tmp_path):
    responses = [
        json.dumps(["任务A", "任务A", "任务B"], ensure_ascii=False),
        "final A已完成",
        "final B已完成",
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    final_text = agent.think("请给我做一个两步任务")
    assert "共 2 项" in final_text

    items = sorted(_list_created_items(agent), key=lambda x: int(x.get("id", 0)))
    assert len(items) == 2
    contents = [it.get("content") for it in items]
    assert contents == ["任务A", "任务B"]


def test_execute_marks_duplicate_responses(monkeypatch, tmp_path):
    responses = [
        json.dumps(["任务A", "任务B"], ensure_ascii=False),
        "final 统一结论",
        "final 统一结论",
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    final_text = agent.think("请执行两个不同任务")
    assert "共 2 项" in final_text

    items = sorted(_list_created_items(agent), key=lambda x: int(x.get("id", 0)))
    assert len(items) == 2

    first_responses = items[0].get("responses") or []
    second_responses = items[1].get("responses") or []
    assert first_responses and second_responses

    first_text = first_responses[-1].get("content")
    second_text = second_responses[-1].get("content")
    assert "统一结论" in first_text
    assert "重复" in second_text


def test_plan_fallback_when_llm_returns_empty(monkeypatch, tmp_path):
    responses = [
        "",
        "final 回退任务执行完成",
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    agent.think("我要一个回退方案")
    items = _list_created_items(agent)
    assert len(items) == 1
    assert "完成用户请求" in str(items[0].get("content"))
