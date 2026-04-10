import json

from frame.agent.summarizer_agent import SummarizerAgent
from frame.core.config import AgentConfig
from frame.core.llm import LLMClient
from frame.core.message import ToolMessage
from frame.tool.todo import TODOTool


class FakeLLM(LLMClient):
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0
        self.prompts = []

    def invoke(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._idx >= len(self._responses):
            return "final 默认总结"
        out = self._responses[self._idx]
        self._idx += 1
        return out


def _add_item(todo, content, status, workflow_id, plan_id, objective):
    add_tr = todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add",
                "content": content,
                "metadata": {
                    "workflow_id": workflow_id,
                    "plan_id": plan_id,
                    "objective": objective,
                },
            },
            phase="call",
        )
    )
    assert add_tr.status == "ok"
    item = add_tr.output
    item_id = int(item["id"])

    if status != "PENDING":
        up_tr = todo.run(
            ToolMessage(
                tool_name="TODO",
                tool_input={
                    "op": "update",
                    "id": item_id,
                    "status": status,
                    "metadata": {
                        "workflow_id": workflow_id,
                        "plan_id": plan_id,
                        "objective": objective,
                    },
                },
                phase="call",
            )
        )
        assert up_tr.status == "ok"

    return item_id


def test_summarizer_agent_generates_goal_aligned_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    todo = TODOTool(storage_path="summarizer_test.json")

    workflow_id = "wf-100"
    plan_id = "plan-100"
    objective = "完成智能指针学习路径并给出阶段总结"

    id1 = _add_item(todo, "理解RAII", "COMPLETED", workflow_id, plan_id, objective)
    id2 = _add_item(todo, "掌握unique_ptr", "COMPLETED", workflow_id, plan_id, objective)
    _add_item(todo, "实践shared_ptr", "PENDING", workflow_id, plan_id, objective)

    # 两条已完成项写入重复结论，验证 Summarizer 上下文会去重
    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add_response",
                "id": id1,
                "response": "模块A完成",
                "metadata": {"workflow_id": workflow_id, "plan_id": plan_id},
            },
            phase="call",
        )
    )
    todo.run(
        ToolMessage(
            tool_name="TODO",
            tool_input={
                "op": "add_response",
                "id": id2,
                "response": "模块A完成",
                "metadata": {"workflow_id": workflow_id, "plan_id": plan_id},
            },
            phase="call",
        )
    )

    fake_llm = FakeLLM(["final 智能指针学习已完成核心里程碑，建议进入综合实战。"])
    agent = SummarizerAgent(
        name="summarizer_test_agent",
        config=AgentConfig(max_rounds=4),
        llm=fake_llm,
        workflow_id=workflow_id,
        todo_tool=todo,
    )

    text = agent.think(json.dumps({"objective": objective, "plan_id": plan_id}, ensure_ascii=False))

    assert "智能指针学习已完成核心里程碑" in text
    assert "进度：总任务 3 项；已完成 2 项" in text
    assert "去重折叠：1 条" in text

    # 验证传给 LLM 的上下文中包含原始目标，且重复结果已被去重
    assert fake_llm.prompts
    prompt = fake_llm.prompts[-1]
    assert objective in prompt
    assert prompt.count("模块A完成") == 1


def test_summarizer_agent_handles_missing_workflow_items(monkeypatch, tmp_path):
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    todo = TODOTool(storage_path="summarizer_empty_test.json")

    _add_item(todo, "其他工作流任务", "COMPLETED", "wf-other", "plan-other", "其他目标")

    agent = SummarizerAgent(
        name="summarizer_empty_agent",
        config=AgentConfig(max_rounds=3),
        llm=FakeLLM(["final 不应被使用"]),
        workflow_id="wf-target",
        todo_tool=todo,
    )

    text = agent.think("请做总结")
    assert "未找到属于 workflow_id=wf-target 的可汇总任务" in text
