# 流式生成中断与恢复设计建议（V1）

日期：2026-04-18

目的：为前端提供可实现的“中断/暂停/恢复”交互与后端接口建议，便于前端在遇到长响应或需要用户中断时安全地停止并在可行时恢复生成。

总体约束与背景
- 当前后端使用 `POST /api/v1/chat/stream`（ReadableStream / SSE 风格）逐步下发 `chunk|paragraph|done` 帧。
- HTTP chunked 流在传输层并不天然支持“暂停并保留模型内部状态以便 later resume”。要实现“无缝恢复”，后端必须保存 LL M 运行时或采样状态（复杂且昂贵）。因此客户端设计应区分“取消/停止（cancel/stop）”与“请求继续（resume）”两类语义，并提供渐进式可选项。

推荐分层方案（优先级）
1. 最小可行（立即可实现） — 客户端本地“Cancel” + 后端短时保持会话记录
   - 行为：客户端在流中点击“暂停/停止”，立即调用 `AbortController.abort()` 取消 fetch；同时（可选）调用 `POST /api/v1/chat/stream/cancel` 告知后端终止生成并标记该 messageId 为已取消。
   - 恢复：客户端若要继续，直接重新发起 `POST /api/v1/chat/stream`，并在 body 中带上 `resumeFromSeq` 或 `resumeHint`（例如最后收到的 seq / lastText），后端尝试基于会话上下文重新接着生成（但不保证与中断前连续性完全一致）。
   - 优点：实现简单、无须后端保存复杂中间态。缺点：恢复并非严格 token-accurate resume，可能重复或跳跃。适用于大多数产品情形。

2. 中级方案（需要后端更改） — 后端保存可重启的生成状态或提供 `resumeToken`
   - 行为：后端在开始生成时返回 `messageId` + 可选 `resumeToken`（或在 `chunk/paragraph` 帧的 meta 中注入 `resumeToken`）。当客户端暂停后，调用 `POST /api/v1/chat/stream/resume` 并提供 `messageId` + `resumeToken`。后端使用保留的生成器上下文或 `resumeToken` 继续生成。
   - 优点：更平滑的续写体验；减少重复输出。缺点：后端复杂度高，需管理模型会话与资源。

3. 最佳实践（实时控制） — 使用 WebSocket 双向通道
   - 行为：使用 WebSocket 建立实时双向会话，客户端可发送控制消息（`pause`/`resume`/`cancel`）而后端可立即响应并保留模型状态在服务端内存或外部快照。
   - 优点：最灵活、低延迟的控制。缺点：需要后端架构支持 WebSocket/连接管理、水平扩展考虑更多。

API 设计建议（REST 风格，兼容现有流式接口）

1) 开始流（现有）
POST /api/v1/chat/stream
Request JSON:
```json
{
  "conversationId": "conv-123",
  "messages": [...],
  "clientRequestId": "optional-uuid"
}
```
Response: text/event-stream 或 chunked JSON，如现行协议帧（chunk/paragraph/done）。返回的第一批 meta 可以包含 `messageId`。

2) 取消/停止（可选，幂等）
POST /api/v1/chat/stream/cancel
Request JSON:
```json
{ "messageId": "m-123", "reason": "user_request" }
```
Response: `{ "status":"ok" }` 或错误信息。后端用于清理资源并记录用户中断。

3) 请求继续（后端若支持 resume）
POST /api/v1/chat/stream/resume
Request JSON:
```json
{ "messageId": "m-123", "resumeToken": "tk-xyz" }
```
Response: 同 `/stream` 的流式输出（继续以帧返回）。

4) 可选查询状态
GET /api/v1/chat/stream/status?messageId=m-123
Response JSON:
```json
{ "messageId":"m-123", "state":"running|cancelled|finished", "lastSeq": 42 }
```

客户端实现要点（前端）
- 流控制对象：为每次 `streamChat` 请求创建并存储 `AbortController` 与 `messageId`（若后端返回）；store 中保存 `activeStream: { controller, messageId, lastSeq, isActive }`。
- UI 行为：
  - 当 `activeStream.isActive === true` 时，发送按钮变为“暂停/停止”样式（并启用）；点击将触发 `controller.abort()` 并可选发 `POST /api/v1/chat/stream/cancel`。
  - 点击“暂停/停止”后将把当前 assistant 消息 `streaming` 标志设为 false（前端可将其视为已“中止”），并允许用户在同一页面再次点击“继续”或“发送”（若后端支持 resume，则发 `/resume`，否则重新发 `/stream`）。
  - 在中断后，UI 显示“已中断（已接收 N 段）”并提供“继续生成”或“重做”按钮。
- 恢复策略：若后端只支持简单重试，客户端应在再次发起 `/stream` 时把历史消息（包括本条助手当前已接收的内容）传回，并可在 body 中带上 `resumeHint` 表明从何处继续。

服务端实现要点（后端）
- 最小方案：实现 `/cancel` 用于中止正在进行的生成（如果后端在后台保存生成器实例）；若后端只是把生成绑定在 HTTP 请求上，则 `cancel` 可作为记录并不真正作用于已断开的连接。
- 中级/高级方案需：
  - 在生成进程中维护可序列化的 resumeToken 或生成器上下文（取决于所用 LLM 接口）；
  - 提供 `resume` 接口根据 `resumeToken` 恢复生成；或者在 resume 请求中重新启动模型并使用 `resumeHint` 在训练/推理上接续。

示例前端交互流程（最小可行）
1. 用户点击发送 → 前端调用 `/stream` 并保存 `controller`。
2. 后端下发增量帧；前端渲染。
3. 用户点击“暂停” → 前端调用 `controller.abort()`；（可选）调用 `/stream/cancel`。
4a. 若用户点击“继续” → 前端重新调用 `/stream` 或 `/resume`（取决后端能力）。
4b. 若用户点击“重发” → 前端重新组装上下文并调用 `/stream`（通常伴随新 messageId）。

推荐路线（短期可交付）
- 先实现客户端的中断与取消（AbortController + 可选 `/cancel` 请求），并在 UI 上把发送按钮切换为“暂停/取消”。
- 与后端约定：当用户希望恢复时，客户端应重新发起 `/stream` 并把当前接收到的文本作为上下文（`messages`），后端以此为起点继续生成（语义上相当于“继续回答”而非精确 token-resume）。
- 如果产品对“零重复、精确续写”有强需求，再推进到“后端保存生成状态 / resumeToken”或“WebSocket 控制通道”。

文档和接口样例已提供，前端可立即实现 UI 层的暂停/取消逻辑；若需要我也可以：
- 1) 在前端 `ChatPage` / `Composer` 中实现发送按钮的切换（Send ↔ Pause），以及 `AbortController` 的 cancel + 可选 `/cancel` 调用；
- 2) 为后端准备一个最小 demo（Python/FastAPI）演示 `cancel` 与 `resume` 的协定样例。

---
文件位置建议：将此文档放置在 `deepresearch/docx/20260418-streaming-interruption-design.md` 以便后端与前端对接。