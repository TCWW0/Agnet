from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frame.agents.react_code_agent import ReactCodeAgent
from frame.core.config import AgentConfig
from frame.core.llm_types import ToolCallMode
from frame.core.message import LLMResponseFunCallMsg, LLMResponseTextMsg, Message


class _FakeReactLLM:
    def __init__(self) -> None:
        self.calls = []

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        on_tool_call_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools or []),
                "sys_instructions": sys_instructions,
                "tool_mode": tool_mode,
            }
        )
        if on_token_callback:
            for ch in "ok":
                on_token_callback(ch)

        step_index = len(self.calls)
        if step_index == 1:
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="read_file",
                    call_id="call_read",
                    arguments_json=json.dumps({"file_path": "main.py"}, ensure_ascii=False),
                )
            ]
        if step_index == 2:
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="apply_patch",
                    call_id="call_patch",
                    arguments_json=json.dumps(
                        {
                            "patch": "\n".join(
                                [
                                    "--- a/main.py",
                                    "+++ b/main.py",
                                    "@@ -1,2 +1,2 @@",
                                    " def answer():",
                                    "-    return 1",
                                    "+    return 2",
                                ]
                            ),
                        },
                        ensure_ascii=False,
                    ),
                )
            ]
        if step_index == 3:
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="run_tests",
                    call_id="call_tests",
                    arguments_json=json.dumps({"pattern": "test_main.py"}, ensure_ascii=False),
                )
            ]
        return [LLMResponseTextMsg(content=f"step-{step_index} [TASK_COMPLETED]")]


class _PrematureFinishLLM:
    def __init__(self) -> None:
        self.calls = []

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        on_tool_call_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools or []),
                "sys_instructions": sys_instructions,
                "tool_mode": tool_mode,
            }
        )
        if on_token_callback:
            for ch in "ok":
                on_token_callback(ch)

        step_index = len(self.calls)
        if step_index == 1:
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="apply_patch",
                    call_id="call_patch",
                    arguments_json=json.dumps(
                        {
                            "patch": "\n".join(
                                [
                                    "--- a/main.py",
                                    "+++ b/main.py",
                                    "@@ -1,2 +1,2 @@",
                                    " def answer():",
                                    "-    return 1",
                                    "+    return 2",
                                ]
                            ),
                        },
                        ensure_ascii=False,
                    ),
                )
            ]
        if step_index == 2:
            return [LLMResponseTextMsg(content="premature [TASK_COMPLETED]")]
        if step_index == 3:
            return [
                LLMResponseFunCallMsg.from_raw(
                    tool_name="run_tests",
                    call_id="call_tests",
                    arguments_json=json.dumps({"pattern": "test_main.py"}, ensure_ascii=False),
                )
            ]
        return [LLMResponseTextMsg(content=f"step-{step_index} [TASK_COMPLETED]")]


class _TextDirectiveLLM:
    def __init__(self) -> None:
        self.calls = []

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        on_tool_call_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools or []),
                "sys_instructions": sys_instructions,
                "tool_mode": tool_mode,
            }
        )
        if on_token_callback:
            for ch in "ok":
                on_token_callback(ch)

        step_index = len(self.calls)
        if step_index == 1:
            return [
                LLMResponseTextMsg(
                    content=json.dumps({"read_file": {"file_path": "main.py"}}, ensure_ascii=False)
                )
            ]
        if step_index == 2:
            return [
                LLMResponseTextMsg(
                    content=json.dumps(
                        {
                            "apply_patch": {
                                "patch": "\n".join(
                                    [
                                        "--- a/main.py",
                                        "+++ b/main.py",
                                        "@@ -1,2 +1,2 @@",
                                        " def answer():",
                                        "-    return 1",
                                        "+    return 2",
                                    ]
                                ),
                            }
                        },
                        ensure_ascii=False,
                    )
                )
            ]
        if step_index == 3:
            return [
                LLMResponseTextMsg(
                    content=json.dumps({"run_tests": {"pattern": "test_main.py"}}, ensure_ascii=False)
                )
            ]
        return [LLMResponseTextMsg(content="[TASK_COMPLETED]")]


class _ErrorThenFinishLLM:
    def __init__(self) -> None:
        self.calls = []

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        on_tool_call_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": list(tools or []),
                "sys_instructions": sys_instructions,
                "tool_mode": tool_mode,
            }
        )
        if on_token_callback:
            for ch in "ok":
                on_token_callback(ch)

        step_index = len(self.calls)
        if step_index == 1:
            return [
                LLMResponseTextMsg(
                    content=json.dumps({"read_file": {"file_path": "missing.py"}}, ensure_ascii=False)
                )
            ]
        if step_index == 2:
            return [
                LLMResponseTextMsg(
                    content=json.dumps(
                        {
                            "apply_patch": {
                                "patch": "\n".join(
                                    [
                                        "--- a/main.py",
                                        "+++ b/main.py",
                                        "@@ -1,2 +1,2 @@",
                                        " def answer():",
                                        "-    return 1",
                                        "+    return 2",
                                    ]
                                ),
                            }
                        },
                        ensure_ascii=False,
                    )
                )
            ]
        if step_index == 3:
            return [
                LLMResponseTextMsg(
                    content=json.dumps({"run_tests": {"pattern": "test_main.py"}}, ensure_ascii=False)
                )
            ]
        return [LLMResponseTextMsg(content="[TASK_COMPLETED]")]


def _write_workspace_files(workspace: Path) -> None:
    (workspace / "main.py").write_text(
        "def answer():\n    return 1\n",
        encoding="utf-8",
    )
    (workspace / "test_main.py").write_text(
        "from main import answer\n\n\n" "def test_answer():\n    assert answer() == 2\n",
        encoding="utf-8",
    )


def test_react_code_agent_runs_read_patch_test_loop(tmp_path) -> None:
    workspace = tmp_path / "react_code"
    workspace.mkdir()
    _write_workspace_files(workspace)

    fake_llm = _FakeReactLLM()
    agent = ReactCodeAgent(
        config=AgentConfig(max_rounds=6),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
        session_id="react-code-agent",
        agent_id="react-code-agent",
    )

    assert {tool.name for tool in agent.tool_registry_.get_tools()} == {
        "read_file",
        "apply_patch",
        "run_tests",
    }
    assert "Thought -> Action -> Observation" in agent.sys_prompt_
    assert str(workspace.resolve()) in agent.sys_prompt_

    agent.think("change answer() to return 2 and verify it")

    assert len(fake_llm.calls) >= 4
    assert fake_llm.calls[0]["tool_mode"] == ToolCallMode.MANUAL
    assert fake_llm.calls[0]["tools"]
    assert (workspace / "main.py").read_text(encoding="utf-8") == "def answer():\n    return 2\n"
    assert "[TASK_COMPLETED]" in agent.history_[-1].content


def test_react_code_agent_parses_text_tool_directives(tmp_path) -> None:
    workspace = tmp_path / "react_code"
    workspace.mkdir()
    _write_workspace_files(workspace)

    fake_llm = _TextDirectiveLLM()
    agent = ReactCodeAgent(
        config=AgentConfig(max_rounds=6),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
    )

    agent.think("change answer() to return 2 and verify it")

    assert len(fake_llm.calls) >= 4
    assert (workspace / "main.py").read_text(encoding="utf-8") == "def answer():\n    return 2\n"
    assert "[TASK_COMPLETED]" in agent.history_[-1].content


def test_react_code_agent_does_not_finish_before_tests_pass(tmp_path) -> None:
    workspace = tmp_path / "react_code"
    workspace.mkdir()
    _write_workspace_files(workspace)

    fake_llm = _PrematureFinishLLM()
    agent = ReactCodeAgent(
        config=AgentConfig(max_rounds=6),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
    )

    agent.think("change answer() to return 2 and verify it")

    assert len(fake_llm.calls) == 4
    assert "[TASK_COMPLETED]" in agent.history_[-1].content


def test_react_code_agent_finishes_after_earlier_tool_error(tmp_path) -> None:
    workspace = tmp_path / "react_code"
    workspace.mkdir()
    _write_workspace_files(workspace)

    fake_llm = _ErrorThenFinishLLM()
    agent = ReactCodeAgent(
        config=AgentConfig(max_rounds=6),
        llm=fake_llm,  # type: ignore[arg-type]
        working_dir=str(workspace),
    )

    agent.think("change answer() to return 2 and verify it")

    assert len(fake_llm.calls) == 4
    assert "[TASK_COMPLETED]" in agent.history_[-1].content
