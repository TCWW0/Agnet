import json

from frame.agent.deep_thought_agent import DeepThoughtAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient


class FakeLLM(LLMClient):
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    def invoke(self, prompt: str) -> str:
        if self._idx >= len(self._responses):
            return "final 默认输出"
        out = self._responses[self._idx]
        self._idx += 1
        return out


def test_deep_thought_agent_basic_orchestration(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))

    responses = [
        'tool_call {"name":"TODO","input":{"ops":[{"op":"add","content":"步骤一"},{"op":"add","content":"步骤二"}]}}',
        "final 已创建 2 条待办",
        "final 步骤一已完成",
        "final 步骤二已完成",
        "final 全部目标已完成，建议进入复盘。",
    ]

    agent = DeepThoughtAgent(
        name="deep_thought_test_agent",
        config=AgentConfig(max_rounds=6),
        llm=FakeLLM(responses),
        workflow_id="wf-deep-01",
    )

    text = agent.think("请把任务分两步并完成")

    assert "全部目标已完成" in text
    assert "执行阶段：已执行 2 轮" in text

    plan_id = agent.last_plan_id_
    assert isinstance(plan_id, str) and plan_id

    items = agent._list_plan_items(plan_id)
    assert len(items) == 2
    assert all(str(it.get("status") or "").upper() == "COMPLETED" for it in items)

    for it in items:
        meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
        assert meta.get("workflow_id") == "wf-deep-01"
        assert meta.get("plan_id") == plan_id
        assert meta.get("objective") == "请把任务分两步并完成"

        responses_data = it.get("responses") or []
        assert isinstance(responses_data, list)
        assert len(responses_data) >= 1
        last = responses_data[-1]
        assert isinstance(last, dict)
        last_meta = last.get("metadata") if isinstance(last.get("metadata"), dict) else {}
        assert last_meta.get("workflow_id") == "wf-deep-01"
