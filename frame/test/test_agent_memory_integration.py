from __future__ import annotations

from typing import List, Optional

from frame.agents.react_agent import ReactAgent
from frame.core.base_agent import BaseAgent
from frame.core.config import AgentConfig
from frame.core.message import LLMResponseTextMsg, Message
from frame.memory.base import AgentMemoryHooks, InMemoryMemoryKernel, MemoryPolicy, MemoryToolFacade, SessionRef
from frame.tool.register import ToolRegistry


class _FakeLLM:
    def __init__(self, name: str):
        self.name = name
        self.last_messages: List[Message] = []

    def invoke_streaming(
        self,
        messages: List[Message],
        tools=None,
        sys_instructions: Optional[str] = None,
        on_token_callback=None,
        tool_mode=None,
    ) -> List[Message]:
        self.last_messages = list(messages)
        last_user = next((msg for msg in reversed(messages) if msg.role == "user"), None)
        prompt = last_user.content if last_user is not None else ""
        response_text = f"{self.name} echo: {prompt}"
        if on_token_callback:
            for ch in response_text:
                on_token_callback(ch)
        return [LLMResponseTextMsg(content=response_text)]


class _TestAgent(BaseAgent):
    def _think_impl(self, user_input: str):
        invoke_messages = self._prepare_invoke_messages(user_input)
        llm_messages = self.llm_.invoke_streaming(invoke_messages)  # type: ignore[call-arg]
        if not llm_messages:
            return
        self._commit_turn(user_input=user_input, llm_messages=llm_messages)


def test_forced_memory_hooks_work_without_tools() -> None:
    kernel = InMemoryMemoryKernel()
    hooks = AgentMemoryHooks(kernel, MemoryPolicy(enable_retrieval=False))
    session = SessionRef(session_id="solo-session")

    fake_llm = _FakeLLM("solo")
    agent = _TestAgent(
        config=AgentConfig(max_rounds=3),
        llm=fake_llm,  # type: ignore[arg-type]
        session_id=session.session_id,
        memory_hooks=hooks,
        agent_id="agent-solo",
    )

    agent.think("remember this")

    stored = kernel.load_recent(session, 10)
    assert any(msg.role == "user" and msg.content == "remember this" for msg in stored)
    assert any(msg.role == "assistant" and "solo echo" in msg.content for msg in stored)


def test_shared_session_visible_across_agents() -> None:
    kernel = InMemoryMemoryKernel()
    hooks = AgentMemoryHooks(
        kernel,
        MemoryPolicy(max_history_items=50, retrieval_top_k=5, enable_retrieval=True),
    )

    agent_a = _TestAgent(
        config=AgentConfig(max_rounds=3),
        llm=_FakeLLM("agent-a"),  # type: ignore[arg-type]
        session_id="shared-session",
        memory_hooks=hooks,
        agent_id="agent-a",
    )
    llm_b = _FakeLLM("agent-b")
    agent_b = _TestAgent(
        config=AgentConfig(max_rounds=3),
        llm=llm_b,  # type: ignore[arg-type]
        session_id="shared-session",
        memory_hooks=hooks,
        agent_id="agent-b",
    )

    agent_a.think("my name is alice")
    agent_b.think("what is my name")

    consumed_contents = [msg.content for msg in llm_b.last_messages]
    assert any("my name is alice" in content for content in consumed_contents)

    stored = kernel.load_recent(SessionRef(session_id="shared-session"), 20)
    assert any(msg.content == "my name is alice" for msg in stored)
    assert any(msg.content == "what is my name" for msg in stored)


def test_react_agent_registers_memory_tools_with_shared_kernel() -> None:
    kernel = InMemoryMemoryKernel()
    hooks = AgentMemoryHooks(
        kernel,
        MemoryPolicy(max_history_items=30, retrieval_top_k=5, enable_retrieval=True),
    )
    memory_facade = MemoryToolFacade(kernel)
    llm = _FakeLLM("react")
    registry = ToolRegistry()

    agent = ReactAgent(
        config=AgentConfig(max_rounds=3),
        llm=llm,  # type: ignore[arg-type]
        tool_registry=registry,
        session_id="shared-react",
        memory_hooks=hooks,
        memory_tool_facade=memory_facade,
        enable_memory_tools=True,
        agent_id="react-agent",
    )

    tool_names = {tool.name for tool in registry.get_tools()}
    assert {"calculater", "memory_recall", "memory_remember", "memory_forget"}.issubset(tool_names)

    remember_tool = registry.get_tool_by_name("memory_remember")
    remember_result = remember_tool.execute({"text": "project codename atlas"})
    assert remember_result.status == "success"

    agent.think("atlas")
    assert any("project codename atlas" in msg.content for msg in llm.last_messages)
