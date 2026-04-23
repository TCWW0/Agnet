from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from frame.agents.code_agent import CodeAgent
from frame.core.config import AgentConfig


class _NoopLLM:
    def invoke_streaming(self, *args, **kwargs):
        return []


def test_code_agent_resolves_relative_workspace_against_repo_root(tmp_path) -> None:
    agent = CodeAgent(
        config=AgentConfig(max_rounds=1),
        llm=_NoopLLM(),  # type: ignore[arg-type]
        working_dir="code_space",
        session_id="workspace-resolution",
        agent_id="code-agent",
    )

    assert agent.workspace_root_.name == "code_space"
    assert str(agent.workspace_root_).endswith("/code_space")
    assert agent.workspace_root_.is_absolute()
