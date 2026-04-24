from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frame.agents.code_agent import CodeAgent
from frame.core.config import AgentConfig
from frame.core.llm_types import ToolCallMode
from frame.core.message import LLMResponseFunCallMsg, LLMResponseTextMsg, Message, ToolResponseMessage
from frame.tool.builtin.todo.models import TodoStatus


class _FakeCodeLLM:
    def __init__(self) -> None:
        self.calls = []

    @staticmethod
    def _phase_from_sys_instructions(sys_instructions: Optional[str]) -> str:
        text = sys_instructions or ""
        if "Analyze the request" in text:
            return "analysis"
        if "Execute the implementation plan" in text:
            return "generation"
        if "Verify the workspace state" in text:
            return "verification"
        return "unknown"

    @staticmethod
    def _has_task_focus(messages: List[Message]) -> bool:
        return any("[Task Focus]" in getattr(msg, "content", "") for msg in messages)

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        on_tool_call_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        phase = self._phase_from_sys_instructions(sys_instructions)
        self.calls.append(
            {
                "phase": phase,
                "messages": list(messages),
                "tools": list(tools or []),
                "sys_instructions": sys_instructions,
                "tool_mode": tool_mode,
            }
        )
        if on_token_callback:
            for ch in "ok":
                on_token_callback(ch)

        if phase == "analysis":
            if any(getattr(msg, "type", "") == "tool_response" and getattr(msg, "tool_name", "") == "todo" for msg in messages):
                return [LLMResponseTextMsg(content=f"analysis-{len(self.calls)}")]
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="todo",
                    call_id=f"analysis-call-{len(self.calls)}",
                    arguments_json=json.dumps(
                        {"action": "create", "text": "draft implementation plan", "status": "not-started"},
                        ensure_ascii=False,
                    ),
                )
            ]

        if phase == "generation":
            if any(getattr(msg, "type", "") == "tool_response" and getattr(msg, "tool_name", "") == "write_file" for msg in messages):
                return [LLMResponseTextMsg(content=f"generation-{len(self.calls)}")]
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="write_file",
                    call_id=f"generation-call-{len(self.calls)}",
                    arguments_json=json.dumps(
                        {"path": "hello.txt", "content": "hello from code agent"},
                        ensure_ascii=False,
                    ),
                )
            ]

        if phase == "verification":
            if any(getattr(msg, "type", "") == "tool_response" and getattr(msg, "tool_name", "") == "list_dir" for msg in messages):
                return [LLMResponseTextMsg(content=f"verification-{len(self.calls)} [TASK_COMPLETED]")]
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="list_dir",
                    call_id=f"verification-call-{len(self.calls)}",
                    arguments_json=json.dumps({"path": "."}, ensure_ascii=False),
                )
            ]

        return [LLMResponseTextMsg(content=f"phase-{len(self.calls)}")]


class _BackpressureLLM:
    def __init__(self) -> None:
        self.calls = []

    @staticmethod
    def _phase_from_sys_instructions(sys_instructions: Optional[str]) -> str:
        text = sys_instructions or ""
        if "Analyze the request" in text:
            return "analysis"
        if "Execute the implementation plan" in text:
            return "generation"
        if "Verify the workspace state" in text:
            return "verification"
        return "unknown"

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        on_tool_call_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        phase = self._phase_from_sys_instructions(sys_instructions)
        self.calls.append(
            {
                "phase": phase,
                "messages": list(messages),
                "tools": list(tools or []),
                "sys_instructions": sys_instructions,
                "tool_mode": tool_mode,
            }
        )
        if on_token_callback:
            for ch in "ok":
                on_token_callback(ch)

        if phase == "verification" and any("[Task Focus]" in getattr(msg, "content", "") for msg in messages):
            return [LLMResponseTextMsg(content=f"verification-{len(self.calls)} [TASK_COMPLETED]")]

        return [LLMResponseTextMsg(content=f"{phase}-{len(self.calls)}")]


def test_code_agent_injects_tools_and_workspace(tmp_path) -> None:
    workspace = tmp_path / "code_space"
    fake_llm = _FakeCodeLLM()
    agent = CodeAgent(
        config=AgentConfig(max_rounds=2),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
        session_id="code-agent-session",
        agent_id="code-agent",
    )

    assert workspace.exists()
    assert "Execution policy" in agent.sys_prompt_
    assert str(workspace.resolve()) in agent.sys_prompt_

    agent.think("create a hello world file")

    analysis_calls = [call for call in fake_llm.calls if call["phase"] == "analysis"]
    generation_calls = [call for call in fake_llm.calls if call["phase"] == "generation"]
    verification_calls = [call for call in fake_llm.calls if call["phase"] == "verification"]

    assert len(analysis_calls) >= 2
    assert len(generation_calls) >= 2
    assert len(verification_calls) >= 2

    assert {tool.name for tool in analysis_calls[0]["tools"]} == {
        "read_file",
        "search",
        "list_dir",
        "todo",
    }
    assert analysis_calls[0]["tool_mode"] == ToolCallMode.MANUAL

    assert {tool.name for tool in generation_calls[0]["tools"]} == {
        "read_file",
        "search",
        "list_dir",
        "todo",
        "write_file",
        "apply_patch",
        "run_command",
        "run_tests",
    }
    assert generation_calls[0]["tool_mode"] == ToolCallMode.MANUAL

    assert {tool.name for tool in verification_calls[0]["tools"]} == {
        "read_file",
        "search",
        "list_dir",
        "todo",
        "run_tests",
    }
    assert verification_calls[0]["tool_mode"] == ToolCallMode.MANUAL

    assert analysis_calls[0]["sys_instructions"]
    assert generation_calls[0]["sys_instructions"]
    assert verification_calls[0]["sys_instructions"]

    items = agent.todo_storage_.load_items()
    assert len(items) == 1
    assert items[0].status == TodoStatus.NOT_STARTED
    assert "draft implementation plan" in items[0].text
    assert (workspace / "hello.txt").exists()
    assert "[TASK_COMPLETED]" in agent.history_[-1].content


def test_code_agent_injects_task_focus_after_idle_rounds(tmp_path) -> None:
    workspace = tmp_path / "code_space"
    fake_llm = _BackpressureLLM()
    agent = CodeAgent(
        config=AgentConfig(max_rounds=2),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
        session_id="code-agent-backpressure",
        agent_id="code-agent",
    )
    agent.task_state_update_backpressure_rounds_ = 1

    agent.think("write a tiny helper and verify it")

    reminder_calls = [
        call
        for call in fake_llm.calls
        if any("[Task Focus]" in getattr(msg, "content", "") for msg in call["messages"])
    ]
    assert reminder_calls
    assert "Rounds without todo state updates" in reminder_calls[0]["messages"][-1].content
    assert "[TASK_COMPLETED]" in agent.history_[-1].content


def test_code_agent_builds_run_tests_not_found_guidance(tmp_path) -> None:
    workspace = tmp_path / "code_space"
    fake_llm = _FakeCodeLLM()
    agent = CodeAgent(
        config=AgentConfig(max_rounds=2),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
    )

    run_tests_error = ToolResponseMessage.from_tool_result(
        tool_name="run_tests",
        call_id="call_1",
        status="error",
        output="no tests ran\nERROR: file or directory not found: test_*.py",
        details={"exit_code": 4, "error_type": "tests_not_found"},
    )

    retry_context = agent._compose_retry_context([], [], [], [run_tests_error])
    hint_text = retry_context[-1].content
    assert "Create a minimal test file first" in hint_text
    assert "Do not repeat read_file/list_dir loops" in hint_text
