# 后端阶段总结（Phase 1）

## 阶段目标

在不修改 `frame` 目录的前提下，于 `deepresearch/backend` 中搭建可联调后端最小架构。

## 已完成

1. 初始化后端目录下的 Python 包结构：`src` + `tests`
2. 定义类型化 API 模型：请求/响应使用 pydantic
3. 实现最小 FastAPI 服务：
   - `GET /health`
   - `POST /api/chat`
   - `POST /api/chat/stream` (SSE)
   - `GET /api/chat/stream` (兼容探测)
4. 实现双引擎机制：
   - `mock` 模式（默认）用于本地联调
   - `frame` 模式预留真实模型能力接入
5. 添加后端 smoke tests（pytest + TestClient）

## 风险与注意事项

1. `frame` 模式依赖 LLM 环境变量（如 `LLM_API_KEY`），若未配置将无法调用真实模型。
2. 当前前端页面仍在本地模拟回包，尚未切换到真实后端请求流程。
3. SSE 已可用，但前端当前 `EventSource` 仅带 `conversationId`，未携带消息体，后续建议改为 `POST + fetch stream`。

## 下一步建议

1. 将 `deepresearch/front/src/pages/ChatPage.tsx` 的模拟回包替换为真实 API 调用。
2. 在前端 service 层统一处理同步/流式返回。
3. 增加简单会话内存（按 conversationId 保存 messages）以支持最小多轮上下文。
