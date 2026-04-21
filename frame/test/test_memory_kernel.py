from __future__ import annotations

from frame.core.message import LLMResponseTextMsg, Message, UserTextMessage
from frame.memory.base import (
    AgentMemoryHooks,
    InMemoryMemoryKernel,
    MemoryPolicy,
    MemoryToolFacade,
    SessionRef,
    build_memory_tools,
)


def test_in_memory_kernel_append_load_query_clear() -> None:
    kernel = InMemoryMemoryKernel()
    session = SessionRef(session_id="session-kernel")

    kernel.append(
        session,
        [
            UserTextMessage(content="hello world"),
            LLMResponseTextMsg(content="hello back"),
            Message(role="assistant", content="this is another sentence"),
        ],
    )

    recent = kernel.load_recent(session, 2)
    assert len(recent) == 2
    assert recent[0].content == "hello back"

    recalled = kernel.query(session, "hello", top_k=3)
    assert recalled
    assert any("hello" in msg.content.lower() for msg in recalled)

    kernel.clear(session, scope="recent")
    assert kernel.load_recent(session, 10) == []


def test_memory_tool_facade_and_tool_adapters_share_kernel() -> None:
    kernel = InMemoryMemoryKernel()
    facade = MemoryToolFacade(kernel)
    session = SessionRef(session_id="session-tool")

    assert facade.remember(session, "user likes coffee") == "ok"
    recalled_direct = facade.recall(session, "coffee", top_k=3)
    assert recalled_direct
    assert any("coffee" in item for item in recalled_direct)

    tools = {tool.name: tool for tool in build_memory_tools(facade, session)}
    remember_result = tools["memory_remember"].execute({"text": "user prefers tea"})
    assert remember_result.status == "success"

    recall_result = tools["memory_recall"].execute({"query": "tea", "top_k": "2"})
    assert recall_result.status == "success"
    assert "tea" in recall_result.output

    forget_result = tools["memory_forget"].execute({"scope": "all"})
    assert forget_result.status == "success"
    assert facade.recall(session, "tea", top_k=2) == []


def test_memory_hooks_deduplicate_recalled_messages() -> None:
    kernel = InMemoryMemoryKernel()
    hooks = AgentMemoryHooks(
        kernel,
        MemoryPolicy(max_history_items=10, retrieval_top_k=3, enable_retrieval=True),
    )
    session = SessionRef(session_id="session-hooks")

    existing = UserTextMessage(content="shared context")
    kernel.append(session, [existing])

    merged = hooks.before_invoke(
        session=session,
        user_input="shared",
        base_messages=[Message(role="system", content="sys"), existing],
    )

    shared_messages = [msg for msg in merged if msg.content == "shared context"]
    assert len(shared_messages) == 1
