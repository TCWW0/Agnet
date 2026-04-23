from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frame.agents.code_agent import CodeAgent
from frame.core.config import AgentConfig
from frame.core.message import LLMResponseTextMsg, Message


class _FakeCodeLLM:
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
        if isinstance(sys_instructions, str) and "Verify the workspace state" in sys_instructions:
            return [LLMResponseTextMsg(content=f"phase-{len(self.calls)} [TASK_COMPLETED]")]
        return [LLMResponseTextMsg(content=f"phase-{len(self.calls)}")]


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
    assert "apply_patch" in agent.sys_prompt_
    assert "run_tests" in agent.sys_prompt_
    assert str(workspace.resolve()) in agent.sys_prompt_

    agent.think("create a hello world file")

    assert len(fake_llm.calls) == 3
    assert fake_llm.calls[0]["tools"] == []
    assert {tool.name for tool in fake_llm.calls[1]["tools"]} >= {
        "read_file",
        "search",
        "apply_patch",
        "run_command",
        "run_tests",
        "git_diff",
        "git_commit",
        "git_reset",
    }
    assert fake_llm.calls[1]["sys_instructions"]
    assert fake_llm.calls[2]["sys_instructions"]
    assert "[TASK_COMPLETED]" in agent.history_[-1].content
