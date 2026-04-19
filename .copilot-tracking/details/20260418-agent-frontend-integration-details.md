<!-- markdownlint-disable-file -->

# Task Details: Agent 前后端联调（第一版）

## Research Reference

**Source Research**: #file:../research/20260417-frontend-chatgpt-style-research.md

## Phase 1: API 与数据契约设计

### Task 1.1: 定义 API 契约

目标：定义简单且可扩展的 HTTP 接口，保证前端能发起消息并接收 assistant 响应（支持同步与流式两种模式）。

- **Endpoints (初版)**
  - `POST /api/chat` — 同步/一次性响应
    - Request JSON: `{ "conversationId": "optional", "messages": [{"role":"user","content":"..."}] }`
    - Response JSON: `{ "message": { "id": "", "role": "assistant", "content": "..." } }`
  - `POST /api/chat/stream` — 返回 chunked HTTP 或 SSE（用于流式增量渲染）
  - (可选) `GET /api/conversations`、`POST /api/conversations`、`GET /api/conversations/:id/messages`

- **Research refs**:
  - API 约定（示例）: #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 168-184)
  - 流式传输示例: #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 127-166)

### Task 1.2: 消息格式映射

- 前端期望消息基本字段：`id`, `role`, `content`（参见 deepresearch/front/docs/frontend-summary.md）
- 后端使用 `frame.core.message.Message`（pydantic），设计 JSON ↔ Message 的双向映射。
- **Research refs**: #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 185-195)

## Phase 2: 后端实现（在 frame 中暴露 HTTP API）

### Task 2.1: 选择框架与服务入口

- 推荐框架：`FastAPI`（轻量、易于本地调试、支持 SSE/Streaming）
- 建议创建 `frame/http_server.py` 负责 HTTP 路由、依赖注入（Agent/LLM 实例）与 CORS 配置。
- **依赖**: `fastapi`, `uvicorn`, `python-multipart` (如需), `aiofiles` (可选)

### Task 2.2: 提供一个 Mock/可替换的 LLM 实现用于本地联调

- 新增 `frame/core/mock_llm.py`（或 `frame/core/dev_llm.py`），实现与 `BaseLLM` 相似的 `invoke` / `invoke_streaming` 接口，但返回可预测的响应（例如回显或固定模板），以便前端联调无需 OpenAI Key。

示例伪代码：

```py
from frame.core.message import LLMResponseTextMsg

class MockLLM:
    def invoke(self, messages, tools=None, **kwargs):
        return [LLMResponseTextMsg(content="（模拟）收到：" + messages[-1].content)]

    def invoke_streaming(self, messages, **kwargs):
        # 可以直接返回完整消息，或模拟分块回传
        return [LLMResponseTextMsg(content="（stream）收到：" + messages[-1].content)]
```

### Task 2.3: 在 frame 中封装 HTTP handler 与 Agent 启动逻辑

- 新建 `frame/http_handlers.py`（或在 `frame/http_server.py` 中实现）
  - 注入 `Agent`（如 `SimpleAgent`）与 `LLM`（生产可用时使用 `BaseLLM`，本地联调时使用 `MockLLM`）
  - POST /api/chat: 接收 messages，调用 `agent.think()` 或直接调用 `llm.invoke()`，返回 JSON
  - POST /api/chat/stream: 根据是否选择 SSE/fetch-stream，逐块发送回调数据（在 FastAPI 中可使用 `EventSourceResponse` 或 `StreamingResponse`）

- **Files (实现建议)**:
  - `frame/http_server.py` — FastAPI app 启动脚本
  - `frame/core/mock_llm.py` — 本地 Mock LLM
  - `frame/agents/http_agent.py` — Agent 初始化封装

## Phase 3: 前端对接（前端修改建议）

### Task 3.1: 新增/修改前端服务调用函数

- 修改：`deepresearch/front/src/services/api.ts` 或 `agentClient.ts`
- 提供两个方法示例：
  - `sendMessage(conversationId, messages)`：POST `/api/chat`，解析返回的完整消息并调用 `useChatStore().addMessage(...)`
  - `sendMessageStream(...)`：POST `/api/chat/stream`，使用 `fetch` + ReadableStream 或 EventSource 接收增量内容并调用 `appendToMessage(messageId, chunk)`

示例 fetch（同步）：

```js
const resp = await fetch('/api/chat', { method: 'POST', body: JSON.stringify({ messages }) });
const body = await resp.json();
// body.message -> { id, role, content }
```

示例 stream（fetch + reader）参考研究文件 (Lines 127-166)

### Task 3.2: Composer -> 调用 API

- 在 `deepresearch/front/src/components/Composer.tsx` 中，替换本地 mock onSend 回调为实际调用 `agentClient.sendMessage`，并在成功返回后把 assistant 的消息写入 `useChatStore`。

## File Operations (建议，不在本阶段实际修改)

- Create (later): `frame/http_server.py` — FastAPI app
- Create (later): `frame/core/mock_llm.py` — Mock LLM 实现
- Create (later): `frame/agents/http_agent.py` — Agent 初始化封装
- Modify (later): `deepresearch/front/src/services/agentClient.ts` — 添加 `sendMessage` / `sendMessageStream`
- Modify (later): `deepresearch/front/src/components/Composer.tsx` — 调用后端并更新 store

## Dependencies

- Backend: `fastapi`, `uvicorn`, `python-dotenv` (可选), `aiohttp` (可选)
- Frontend: 使用现有 `deepresearch/front`（Vite + React + TS）依赖

## Success Criteria

- 前端能在开发环境中发送一条用户消息并收到后端返回的 assistant 消息（显示在 ChatWindow）
- 若使用流式接口：前端能实时追加增量 token（调用 `appendToMessage`）
- 后端可切换真实 `BaseLLM`（需要 OpenAI API key）或 `MockLLM`，无需改动前端

## 备注与风险

- 若选择直接使用 `BaseLLM`，需要在开发机设置 OpenAI API Key 与网络出口；建议默认使用 `MockLLM` 进行首次联调。
- CORS 与端口配置（Vite: 5173，FastAPI: 8000）需处理跨域问题（建议在 FastAPI 中添加 CORS middleware）。
