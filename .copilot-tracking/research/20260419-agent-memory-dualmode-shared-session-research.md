<!-- markdownlint-disable-file -->

# Task Research Notes: Frame Agent Memory Dual-Mode + Shared Session

## Research Executed

### File Analysis

- frame/memory/base.py
  - 文件为空，记忆子系统尚未有任何抽象/实现，可低风险引入新接口。
- frame/core/base_agent.py
  - Agent 当前只维护 `history_`，且 `think -> _think_impl` 是统一调度入口，适合挂载“强制记忆 pre/post hook”。
- frame/agents/react_agent.py
  - 每轮会把 `user/assistant/function/tool_response` 回写 `history_`，说明工具相关消息已在本地上下文链路中。
- frame/agents/tool_aware_agent.py
  - 同样依赖 `history_` + `global_tool_registry`，可复用“共享单例资源”模式扩展到 `global_memory_registry`。
- frame/core/base_llm.py
  - 请求级 `workflow_id` 通过 logger 临时绑定后恢复；当前仅是请求追踪，不是业务会话标识。
- frame/core/llm_orchestrator.py
  - `previous_response_id` 仅用于一次 invoke 内工具轮次续调，不承担跨轮持久会话。
- frame/core/openai_adapter.py
  - 统一封装 `build_message_input_items/build_function_call_outputs`，是记忆注入与写回的稳定边界层。
- frame/tool/register.py
  - 已有 `global_tool_registry`，证明框架接受共享资源实例模式。
- frame/core/logger.py
  - 文档明确 logger 可跨 Agent 复用并动态切换 `workflow_id`，可借鉴其“上下文标识注入”做 session 绑定。

### Code Search Results

- history_|session|workflow_id
  - `frame/**/*.py` 检索显示：`history_` 广泛用于 Agent，对话状态集中在 Agent 实例内；`workflow_id` 仅在 logger/LLM 请求层使用。
- global_tool_registry|tool_registry
  - 命中 `react_agent.py`/`tool_aware_agent.py`/`tool/register.py`，确认共享资源模式已成型。
- previous_response_id
  - 命中 `llm_orchestrator.py` 与 `openai_adapter.py`，使用范围为单次编排内部后续请求。
- memory
  - `frame/memory/base.py` 为空，暂无既有实现需要兼容。

### External Research

- #githubRepo:"openai/openai-agents-python sessions session sharing previous_response_id"
  - 官方 sessions 文档与源码均给出“不同 agents 可共享同一个 session”示例；并明确 sessions 不能与 `conversation_id/previous_response_id/auto_previous_response_id` 同时用于同一次运行。
- #githubRepo:"microsoft/autogen AssistantAgent memory update_context MemoryQueryEvent"
  - AutoGen 在 Agent 主流程中先 `update_context` 再模型调用，同时保留工具调用路径；同一 memory 协议同时服务“规则注入”和“工具相关执行上下文”。
- #githubRepo:"langchain-ai/docs short-term-memory ToolRuntime runtime.store"
  - LangChain/LangGraph 将短期记忆作为运行时状态在每步前读取、每步后更新；工具通过 `ToolRuntime` 读写同一状态/存储，实现“主流程强制 + 工具可访问”并存。
- #fetch:https://openai.github.io/openai-agents-python/sessions/
  - 会话行为为“每轮前读历史、每轮后写新增项”；提供历史合并回调与限制提取条数；文档包含 session sharing 场景。
- #fetch:https://developers.openai.com/api/docs/guides/conversation-state
  - OpenAI 提供手动 history、`previous_response_id`、`conversation` 三类会话状态模式；强调上下文窗口管理与压缩。
- #fetch:https://developers.openai.com/api/reference/resources/responses/methods/create
  - `previous_response_id` 与 `conversation` 互斥（cannot be used in conjunction），需在应用层明确单一会话策略。
- #fetch:https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/memory.html
  - Memory 协议核心方法 `add/query/update_context/clear/close`，且 `update_context` 专门用于模型调用前注入。
- #fetch:https://docs.langchain.com/oss/python/langchain/short-term-memory
  - 短期记忆以线程（thread_id）隔离；支持工具读写状态、before/after model 处理中间件。
- #fetch:https://docs.langchain.com/oss/python/langchain/long-term-memory
  - 长期记忆通过统一 store（namespace+key）暴露给 agent 与 tools，强调同一存储内核多入口访问。

### Project Conventions

- Standards referenced: `frame` 当前采用 Pydantic 类型对象 + adapter/orchestrator 分层；Agent 层承担业务编排；共享资源采用全局注册器模式。
- Instructions followed: `.github/skills/project-learn/SKILL.md`（渐进式、可读优先、先简单后迭代）；workspace 配置 `pytest.ini`（pytest 测试约定）与 `requirements.txt`（openai/pydantic/pytest）。另外，`copilot/` 目录不存在，`.github/instructions/` 当前为空。

## Key Discoveries

### Project Structure

当前框架最关键事实：

1. 对话状态真实单一来源是 Agent 的 `history_`（不是 LLM 层）。
2. BaseLLM 的 `workflow_id` 是请求追踪标识，不是会话标识。
3. orchestrator 的 `previous_response_id` 只在单次调用内续调工具，不应直接当成跨轮会话主键。
4. 共享对象范式已存在（`global_tool_registry`），可平移到共享记忆后端。

### Implementation Patterns

针对“规则强制调用 + LLM Tool 调用共用同一记忆系统”的可行模式已被多框架验证：

- 主流程强制路径：调用前注入（load/query/trim/summarize），调用后写回（append/commit）。
- 工具可调用路径：工具只作为门面（query/remember/forget），底层复用同一 memory kernel。
- 会话共享路径：多个 Agent 持有同一个 `session_id` + 同一个 memory backend，即可共享上下文。

已排除路径：

- 仅 Tool 方案：无法保证每轮都触发，违反“规则性强制调用”要求。
- 仅 Hook 方案：满足确定性但无法支持“LLM 自主记忆操作”能力。

### Complete Examples

```python
from __future__ import annotations

from typing import List, Optional, Protocol, Sequence, Literal
from pydantic import BaseModel, Field
from frame.core.message import Message


class SessionRef(BaseModel):
    session_id: str
    # 用于多Agent共享同一会话时的来源标识（可选）
    agent_id: Optional[str] = None


class MemoryPolicy(BaseModel):
    max_history_items: int = 80
    retrieval_top_k: int = 5
    enable_retrieval: bool = True


class MemoryKernel(Protocol):
    """单一记忆内核：强制钩子与Tool门面都走这里。"""

    def load_recent(self, session: SessionRef, limit: int) -> List[Message]: ...
    def query(self, session: SessionRef, text: str, top_k: int) -> List[Message]: ...
    def append(self, session: SessionRef, messages: Sequence[Message]) -> None: ...
    def clear(self, session: SessionRef, scope: Literal["all", "recent", "facts"] = "all") -> None: ...


class AgentMemoryHooks:
    """规则性强制入口：每轮必经。"""

    def __init__(self, kernel: MemoryKernel, policy: MemoryPolicy):
        self.kernel = kernel
        self.policy = policy

    def before_invoke(self, session: SessionRef, user_input: str, base_messages: List[Message]) -> List[Message]:
        history = self.kernel.load_recent(session, self.policy.max_history_items)
        if self.policy.enable_retrieval:
            recalled = self.kernel.query(session, user_input, self.policy.retrieval_top_k)
            return history + recalled + base_messages
        return history + base_messages

    def after_invoke(self, session: SessionRef, new_messages: Sequence[Message]) -> None:
        self.kernel.append(session, new_messages)


class MemoryToolFacade:
    """LLM可见工具入口：内部仍然调用同一 kernel。"""

    def __init__(self, kernel: MemoryKernel):
        self.kernel = kernel

    def remember(self, session: SessionRef, text: str) -> str:
        self.kernel.append(session, [Message(role="system", content=text)])
        return "ok"

    def recall(self, session: SessionRef, query: str, top_k: int = 3) -> List[str]:
        return [m.content for m in self.kernel.query(session, query, top_k)]
```

### API and Schema Documentation

本次约束下的接口草案（MVP级，支持双模+共享会话）：

- `BaseAgent` 会话化字段
  - `session_id_: str`（必有，默认自动生成）
  - `session_ref_: SessionRef`（可含 `agent_id`）
  - `memory_hooks_: AgentMemoryHooks | None`
- `MemoryKernel`（核心唯一后端接口）
  - `load_recent(session, limit)`
  - `query(session, text, top_k)`
  - `append(session, messages)`
  - `clear(session, scope)`
- `AgentMemoryHooks`（强制路径）
  - `before_invoke(session, user_input, base_messages) -> injected_messages`
  - `after_invoke(session, new_messages) -> None`
- `MemoryToolFacade`（Tool路径）
  - `remember(session, text)`
  - `recall(session, query, top_k)`
  - `forget(session, scope)`（可选）

关键边界约束（来自外部规范）：

- 采用应用层会话内存时，应避免在同一运行再叠加 `conversation`/`previous_response_id` 作为跨轮主状态源。
- `previous_response_id` 保留在 orchestrator 单次调用内部续调，不升级为业务 session 机制。

### Configuration Examples

```yaml
memory:
  enabled: true
  backend: in_memory
  policy:
    max_history_items: 80
    enable_retrieval: true
    retrieval_top_k: 5
  tool_facade:
    enabled: true
    expose_tools:
      - memory.recall
      - memory.remember
  session:
    id_source: agent_or_external
    allow_multi_agent_share: true
    # 对齐现有全局共享模式，允许注入全局实例
    registry_mode: global_memory_registry
```

### Technical Requirements

- 必须引入显式 `session_id`，并从“日志追踪ID”与“业务会话ID”解耦。
- 同一 `MemoryKernel` 必须同时被 hook 路径与 tool 路径调用，禁止双后端分叉。
- 多 Agent 共享通过“同 session_id + 同 backend 实例”实现，先不引入复杂分布式一致性。
- 首版只做短期会话消息记忆 + 可选简单检索；长期语义记忆后续增量扩展。
- 测试需覆盖：
  - 无工具调用时，强制记忆仍生效。
  - 有工具调用时，工具与强制路径读到同一份数据。
  - 两个 Agent 同 session_id 能看到同一上下文。

## Recommended Approach

采用单一方案：**Unified Memory Kernel + Dual Access Surfaces**。

实现原则：

1. **内核唯一**：所有记忆读写统一通过 `MemoryKernel`。
2. **入口双模**：
   - 规则强制：`AgentMemoryHooks.before_invoke/after_invoke` 每轮执行。
   - LLM工具：`MemoryToolFacade` 暴露给模型，但内部调用同一内核。
3. **会话显式化**：在 `BaseAgent` 增加 `session_id`；支持外部传入同一 ID 以共享会话。
4. **共享机制对齐现有风格**：新增 `global_memory_registry`（与 `global_tool_registry` 风格一致），减少接入心智成本。
5. **状态边界清晰**：跨轮状态由应用层 session/memory 管理；`previous_response_id` 仅保留在单次工具轮次编排。

该方案在当前仓库改动面最小、与既有架构最一致，并完整覆盖用户提出的两项新增约束。

## Implementation Guidance

- **Objectives**: 让同一记忆系统同时支持强制调用与工具调用，并在 BaseAgent 层完成显式会话化与多Agent共享能力。
- **Key Tasks**: 在 `frame/memory` 定义 `SessionRef/MemoryPolicy/MemoryKernel/AgentMemoryHooks/MemoryToolFacade`；BaseAgent 新增 session 字段与 hooks 调用点；提供全局 memory registry；补充三类核心测试（强制路径、双模一致性、跨Agent共享）。
- **Dependencies**: 现有 `Message` 模型、`BaseAgent` 调度入口、`ToolRegistry` 共享范式、`pytest`。
- **Success Criteria**: 不依赖工具触发也能稳定记忆；工具与强制路径结果一致；同 `session_id` 的多Agent可共享上下文；未引入 `conversation/previous_response_id` 的跨轮双状态冲突。