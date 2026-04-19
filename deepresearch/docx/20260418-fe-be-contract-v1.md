# 前后端联调契约（V1）

## 目标

实现“前端发送消息 -> 后端处理 -> 前端显示 assistant 回复”的最小闭环。

## Endpoint 约定

### 1) 健康检查

- Method: `GET`
- Path: `/api/v1/health`
- Response:
```json
{
  "status": "ok",
  "mode": "mock"
}
```

### 2) 同步回复

- Method: `POST`
- Path: `/api/v1/chat`
- Request:

```json
{
  "conversationId": "optional",
  "messages": [
    { "id": "1", "role": "user", "content": "你好" }
  ]
}
```

- Response:

```json
{
  "message": {
    "id": "assistant-message-id",
    "role": "assistant",
    "content": "(mock) 我收到了你的消息：你好"
  }
}
```

### 3) 流式回复（SSE）

- Method: `POST`
- Path: `/api/v1/chat/stream`
- Request: 与 `/api/chat` 相同
- Response: `text/event-stream`
  - `event: chunk` + `data: <JSON frame>`
  - `event: paragraph` + `data: <JSON frame>`
  - `event: done` + `data: <JSON frame>`
  - 失败场景可返回 `event: error` + `data: <JSON frame>`

示例（chunk）：

```json
{
  "protocolVersion": "1.0",
  "type": "chunk",
  "messageId": "assistant-message-id",
  "seq": 1,
  "role": "assistant",
  "format": "markdown",
  "text": "这是增量文本",
  "timestamp": "2026-04-18T00:00:00Z"
}
```

示例（paragraph）：

```json
{
  "protocolVersion": "1.0",
  "type": "paragraph",
  "messageId": "assistant-message-id",
  "seq": 2,
  "paragraphId": "p1",
  "role": "assistant",
  "format": "markdown",
  "text": "这是一个完整段落。",
  "timestamp": "2026-04-18T00:00:01Z"
}
```

示例（done）：

```json
{
  "protocolVersion": "1.0",
  "type": "done",
  "messageId": "assistant-message-id",
  "seq": 3,
  "role": "assistant",
  "timestamp": "2026-04-18T00:00:02Z",
  "meta": {
    "paragraphCount": 1
  }
}
```

## 前端落地建议

1. 保留 `/api/chat` 作为首版稳定路径。
2. 流式升级时改用 `fetch + ReadableStream`（因为 `EventSource` 仅支持 GET，不适合携带消息体）。
3. `useChatStore` 中继续使用：
   - `addMessage` 添加用户消息/assistant 占位
   - `appendToMessage` 处理 chunk 追加

## 兼容性说明

后端保留 `GET /api/chat/stream` 仅用于现有前端草稿中的 EventSource 探测，不建议作为最终交互协议。
