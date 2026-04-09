import json

from frame.agent.todo_agent import TODOAgent
from frame.core.config import AgentConfig
from frame.core.message import ToolMessage
from frame.core.llm import LLMClient

class FakeLLM(LLMClient):
    def __init__(self, responses):
        self._responses = list(responses)
        self._idx = 0

    def invoke(self, prompt: str) -> str:
        if self._idx >= len(self._responses):
            return "final 测试结束"
        out = self._responses[self._idx]
        self._idx += 1
        return out


def _build_agent(monkeypatch, tmp_path, responses):
    # 将 TODO 持久化目录指向 pytest 临时目录，避免污染真实数据
    monkeypatch.setenv("TODO_JSON_PATH", str(tmp_path))
    llm = FakeLLM(responses)
    return TODOAgent("todo_test_agent", AgentConfig(max_rounds=8), llm)


def test_todo_agent_prompt_is_concise_and_contains_required_specs(monkeypatch, tmp_path):
    agent = _build_agent(monkeypatch, tmp_path, ["final ok"])
    prompt = agent.init_sys_prompt()

    assert "可用工具: TODO" in prompt
    assert "TODOTool 说明" in prompt
    assert "ToolResult" in prompt
    # 软性约束：提示词应保持简洁，避免过长占用 token
    assert len(prompt) < 3000


def test_todo_agent_think_impl_can_add_and_list_items(monkeypatch, tmp_path):
    responses = [
        "think 我先拆分任务",
        'tool_call {"name":"TODO","input":{"op":"add","content":"梳理需求"}}',
        'tool_call {"name":"TODO","input":{"op":"add","content":"实现并自测"}}',
        "final 已完成待办拆分",
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    final_text = agent.think("帮我规划一个开发任务")
    assert "已完成待办拆分" in final_text

    list_result = agent.tool_registry.invoke(
        "TODO",
        ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"),
    )
    assert list_result.status == "ok"
    assert isinstance(list_result.output, list)
    contents = [it.get("content") for it in list_result.output if isinstance(it, dict)]
    assert "梳理需求" in contents
    assert "实现并自测" in contents


def test_todo_agent_rejects_non_todo_tool(monkeypatch, tmp_path):
    responses = [
        'tool_call {"name":"Calculator","input":{"operation":"add","operand1":1,"operand2":2}}'
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    final_text = agent.think("请帮我算一下")
    assert "执行失败" in final_text
    assert "only TODO tool is allowed" in final_text

    # 验证历史中确实记录了 tool_result 且为 error
    tool_result_msgs = [
        h for h in agent.history
        if getattr(h, "role", None) == "system" and getattr(h, "action", None) == "tool_result"
    ]
    assert tool_result_msgs

    last = tool_result_msgs[-1]
    idx = last.content.find("{")
    assert idx >= 0
    parsed = json.loads(last.content[idx:])
    assert parsed.get("status") == "error"


def test_todo_agent_can_handle_batch_tool_call(monkeypatch, tmp_path):
    responses = [
        "think 我将一次性写入 3 条待办",
        'tool_call {"name":"TODO","input":{"ops":[{"op":"add","content":"学习RAII"},{"op":"add","content":"学习unique_ptr"},{"op":"add","content":"学习shared_ptr"}]}}',
        "final 已完成批量待办创建",
    ]
    agent = _build_agent(monkeypatch, tmp_path, responses)

    final_text = agent.think("请帮我设计一个C++智能指针学习方案")
    assert "已完成批量待办创建" in final_text

    list_result = agent.tool_registry.invoke(
        "TODO",
        ToolMessage(tool_name="TODO", tool_input={"op": "list"}, phase="call"),
    )
    assert list_result.status == "ok"
    assert isinstance(list_result.output, list)
    contents = [it.get("content") for it in list_result.output if isinstance(it, dict)]
    assert "学习RAII" in contents
    assert "学习unique_ptr" in contents
    assert "学习shared_ptr" in contents
