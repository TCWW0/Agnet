<!-- markdownlint-disable-file -->

# Task Research Notes: Frame Agent Memory MVP Architecture

## Research Executed

### File Analysis

- frame/memory/base.py
  - 当前文件为空，仓库尚未落地任何记忆抽象或实现。
- frame/core/base_agent.py
  - `history_` 为当前唯一会话上下文容器；Agent 初始化时写入 system message，后续由各Agent在 `_think_impl` 中追加。
- frame/agents/react_agent.py
  - 每轮将 `user`、`assistant text`、`function`、`tool_response` 全部回写 `history_`，说明“消息序列”已具备作为短期记忆源的结构基础。
- frame/agents/simple_agent.py
  - 直接把 `history_` 传给 `BaseLLM.invoke_streaming`，未见会话级持久化或裁剪策略。
- frame/core/llm_orchestrator.py
  - 仅在单次调用内部使用 `previous_response_id` 串联工具轮次；并未承担跨turn记忆存储职责。
- frame/core/openai_adapter.py
  - 采用 adapter 隔离 OpenAI payload，`build_message_input_items` 与 `build_function_call_outputs` 可作为记忆注入与回写的稳定边界。
- frame/tool/base.py
  - 工具协议清晰但偏“按需调用”；若把核心记忆职责放进工具，存在被模型忽略或调用时机不可控的问题。
- frame/core/llm_types.py
  - 通过 Pydantic 统一类型，适合新增 MemoryEntry/MemoryQuery 类型并保持可测试性。

### Code Search Results

- history_
  - 命中 `frame/core/base_agent.py` 与 3 个 agent 实现，确认记忆入口当前集中在 Agent 内部消息列表。
- previous_response_id
  - 命中 `frame/core/llm_orchestrator.py` 与 `frame/core/openai_adapter.py`，确认其作用域仅为“单次编排中的连续请求”。
- build_message_input_items|build_function_call_outputs
  - 命中 `frame/core/openai_adapter.py` 与 `frame/core/llm_orchestrator.py`，可作为 Memory 注入与写回的结构化扩展点。
- memory|Memory (frame/**/*.py)
  - 未发现有效实现，说明当前记忆系统设计空间完整、技术债较低。

### External Research

- #githubRepo:"openai/openai-agents-python session protocol get_items add_items"
  - `Session` 协议最小操作为 `get_items/add_items/pop_item/clear_session`，体现“先做统一存取接口，再替换后端”的演进路径。
- #githubRepo:"microsoft/autogen Memory protocol add query update_context"
  - AutoGen `Memory` 协议把记忆分为 `add/query/update_context/clear/close`，并提供 `ListMemory` 作为简单可预测的MVP实现。
- #githubRepo:"langchain-ai/langchain BaseChatMessageHistory add_messages"
  - 强调 history 抽象与批量写入接口，且在新架构中把状态与工具调用解耦，避免旧记忆抽象与原生tool-calling冲突。
- #fetch:https://developers.openai.com/api/docs/guides/conversation-state
  - 官方建议会话状态可手动拼 history、或用 `previous_response_id`/`conversation`；并明确上下文窗口管理与压缩是必要议题。
- #fetch:https://developers.openai.com/api/reference/resources/responses/methods/create
  - `previous_response_id` 与 `conversation` 不能同时使用；`instructions` 不会在 `previous_response_id` 链上自动继承，提示记忆注入应在应用层显式控制。
- #fetch:https://openai.github.io/openai-agents-python/sessions/
  - 会话内存由 runner 在调用前读历史、调用后写新增项；并明确“session 不应与 conversation_id/previous_response_id 混用”。
- #fetch:https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/memory.html
  - `ListMemory` 先保证可解释性，再扩展向向量库；`update_context` 作为“调用前注入”机制非常关键。
- #fetch:https://docs.langchain.com/oss/python/langchain/short-term-memory
  - 短期记忆与线程绑定，支持调用前裁剪/总结；强调长上下文下必须有 trim/summarize 策略。
- #fetch:https://docs.langchain.com/oss/python/langchain/long-term-memory
  - 长期记忆建议独立 store（namespace + key），并通过工具按需读写，形成“核心记忆模块 + 工具访问层”的组合范式。

### Project Conventions

- Standards referenced: `frame` 采用 Pydantic 类型化数据结构与 Adapter 分层；`BaseTool` 协议独立于核心编排；测试基于 `pytest`。
- Instructions followed: 参考 `.github/skills/project-learn/SKILL.md` 的“简洁可读、可迭代MVP”原则；参考 `python-project-design` 的“强类型+单一数据流+适配器隔离”约束。

## Key Discoveries

### Project Structure

当前 `frame` 的真实数据流是：

1. Agent 在 `_think_impl` 里把用户输入追加到 `history_`。
2. `BaseLLM` 将 `history_` 转为 `InvocationRequest(messages=...)`。
3. `LLMInvocationOrchestrator` 负责工具循环与 `previous_response_id` 串联。
4. Agent 把返回文本/函数调用/工具响应重新追加 `history_`。

因此，MVP记忆最稳妥的接入点是 Agent 层的“调用前读 + 调用后写”，而不是把记忆下沉到 tool 调用路径中。

### Implementation Patterns

- 现有框架天然具备“短期记忆原始材料”（完整 Message 序列），缺的是“可替换存储层 + 检索/裁剪策略”。
- 工具机制是能力扩展层，不适合作为核心会话状态唯一载体；否则会受到模型是否触发工具调用的随机性影响。
- 最符合现状与MVP目标的模式是：
  - 记忆作为独立模块（deterministic, always-on）
  - 可选提供 MemoryTool（LLM-initiated, user-visible memory ops）

### Complete Examples

```python
# Source-derived minimal lifecycle from frame/core/base_agent.py + agents/react_agent.py
class BaseAgent(ABC):
    def __init__(...):
        self.history_: List[Message] = []
        self.history_.append(Message(role="system", content=self.sys_prompt_))

class ReactAgent(BaseAgent):
    def _think_impl(self, user_input: str):
        self.history_.append(UserTextMessage(content=user_input))
        messages = self.llm_.invoke_streaming(self.history_, tools, self.sys_prompt_)
        for msg in messages:
            self.history_.append(msg)
```

### API and Schema Documentation

MVP建议采用以下最小协议（与当前 `Message` / Pydantic 风格对齐）：

- `MemoryStore`（独立模块）
  - `load(session_id: str) -> list[Message]`
  - `append(session_id: str, messages: list[Message]) -> None`
  - `query(session_id: str, text: str, limit: int = 5) -> list[Message]`（MVP可先做关键词）
  - `clear(session_id: str) -> None`
- `MemoryPolicy`（调用策略）
  - `max_history_items`
  - `enable_summary`
  - `summary_trigger_items`

OpenAI约束（影响设计边界）：

- `previous_response_id` 与 `conversation` 互斥。
- 若采用应用层 MemoryStore，则应避免在同一次运行再叠加服务端会话状态管理，防止双重状态源。

### Configuration Examples

```yaml
# MVP memory config example
memory:
  mode: local_module
  backend: in_memory
  session_id_source: agent_instance
  max_history_items: 80
  retrieval:
    enabled: true
    strategy: keyword
    top_k: 5
  summarize:
    enabled: false
```

### Technical Requirements

- 需要一个稳定的 `session_id` 概念（即便MVP先默认每个Agent实例一个session）。
- 必须明确“短期记忆（会话messages）”和“长期记忆（偏好/事实）”分层，避免一开始混在一起。
- 需要调用前注入策略：固定窗口 + 可选检索，不依赖模型主动调用工具。
- 需要可观测性：至少记录 memory hit/miss、注入条数、裁剪条数。
- 需要与现有 tool calling 保持兼容：工具消息必须成对完整（assistant function call + tool response）。

## Recommended Approach

选择“独立记忆模块优先，工具封装次之”的单一路径：

1. 在 `frame/memory` 先落地独立的 `MemoryStore + MemoryPolicy + MemoryManager`。
2. Agent 生命周期改为：
   - 调用前：`load + (window/retrieval)` 注入到本轮 `messages`
   - 调用后：把新增消息批量 `append`
3. MVP后端先用内存字典（可选JSON落盘），保证简单可测。
4. 当你需要“让模型主动记/查”时，再提供 `MemoryTool` 作为门面，内部仍调用 `MemoryManager`。

理由：

- 核心上下文注入必须确定性执行，不应依赖模型是否触发工具。
- 该方案与当前 `history_ -> BaseLLM -> Orchestrator` 主链最小冲突，改造成本最低。
- 后续可平滑演进到 Redis/SQLite/向量检索，而不破坏 Agent 与 Tool 抽象边界。

## Implementation Guidance

- **Objectives**: 在不改变现有工具编排逻辑前提下，为 frame 提供可插拔、可观测、可演进的MVP记忆能力。
- **Key Tasks**: 定义 Memory 接口与数据模型；在 Agent 层增加 pre/post hooks；实现 InMemory 后端与基础检索；补齐单测（加载、追加、裁剪、工具消息完整性）。
- **Dependencies**: 现有 `Message`/`InvocationRequest` 类型；Pydantic；pytest。
- **Success Criteria**: 多轮对话可稳定复现上下文记忆；在关闭模型工具调用时记忆仍生效；切换后端无需改 Agent 业务代码。