# 流式 LLM 输出的前后端语义化协议（V1）

日期：2026-04-18

目的：定义前后端在流式（streaming）场景下交换 LLM 响应时的“语义化”输出格式和处理约定，确保前端能可靠地按段落/块渲染 Markdown 内容，并在断线或降级场景下回退兼容。

设计原则
- 可渐进部署：优先支持后端在流外包装帧（server-side framing），同时兼容最小侵入的 in-band token（控制字符或占位符）。
- 安全稳健：前端不要完全信任模型直接产出的 JSON/标记，服务端应做必要封装与校验。
- 向后兼容：客户端需对纯文本、SSE event、NDJSON 三种常见形式都有回退解析能力。

一、总体协议概念

1) 协议模式（两类，按后端侵入程度排序）
- A — 结构化流（推荐）：后端把 LLM 的输出封装为结构化帧（JSON），通过流式传输（SSE 或 NDJSON）发送给客户端。帧包含 `type`（chunk/paragraph/meta/done/error）、`messageId`、`seq`、`text` 等字段。
- B — 内联分隔符（可选的轻量方案）：后端/系统提示在模型输出文本中插入约定好的不可见分隔符（例如 U+001E 或 `<|PARA|>`），客户端按该分隔符划分段落。

2) 传输通道
- 支持 SSE（text/event-stream）或普通 HTTP chunked（ReadableStream + Fetch）。也可采用 WebSocket。关键在于每个数据帧能逐步到达客户端并被解析。

二、帧（frame）规范（结构化流）

通用 JSON 帧字段

{
  "protocolVersion": "1.0",
  "type": "chunk|paragraph|meta|done|error|heartbeat",
  "messageId": "<string>",      // 服务端给本条 assistant 消息分配的 id
  "seq": 1,                       // 单帧的递增序号（用于重排序/去重）
  "paragraphId": "p1",          // 可选：段落 id（用于 paragraph 类型）
  "role": "assistant|user",     // 来源角色
  "format": "markdown|text",    // 内容格式，优先使用 markdown
  "text": "...",               // chunk/paragraph 的文本内容
  "timestamp": "2026-04-18T...Z",
  "meta": { ... }                // 可选扩展字段
}

字段说明
- `type`：
  - `chunk`：增量文本片段（可能在句中）。
  - `paragraph`：完整段落边界，`text` 为该段最终文本（客户端可把它渲染为单独块并做 Markdown 渲染）。
  - `meta`：可用于传回来源信息、评分、引用等结构化元数据。
  - `done`：消息完成标记，`meta` 可包含最终 messageId 或其它信息。
  - `error`：流中出现错误，包含 `meta.error`。

三、传输示例

a) SSE（event 名称示例）

event: chunk
data: {"protocolVersion":"1.0","type":"chunk","messageId":"m1","seq":1,"text":"这是部分文本...","format":"markdown"}

event: paragraph
data: {"protocolVersion":"1.0","type":"paragraph","messageId":"m1","paragraphId":"p1","seq":3,"text":"这是一个完整段落。","format":"markdown"}

event: done
data: {"protocolVersion":"1.0","type":"done","messageId":"m1","seq":999}

b) NDJSON（每行一个 JSON 对象）

{"protocolVersion":"1.0","type":"chunk","messageId":"m1","seq":1,"text":"第一段前半...","format":"markdown"}

{"protocolVersion":"1.0","type":"paragraph","messageId":"m1","paragraphId":"p1","seq":3,"text":"完整段落文本","format":"markdown"}

{"protocolVersion":"1.0","type":"done","messageId":"m1","seq":999}

四、轻量内联分隔符方案（B）

- 建议使用不可见控制字符 U+001E (Record Separator) 或经 URL/JSON 安全转义的 `<|PARA|>` 作为段落分隔符。例：

  "第一段文本。\u001E第二段文本。"

- 客户端解析规则：收到 chunk 后把 buffer 与分隔符做 split，所有完整段落立即 flush（作为完整段落渲染）；保留最后一个不完整片段等待后续 chunk。

五、前端实现建议（客户端职责）

1) 解析优先级
- 首先尝试把 incoming data parse 为 JSON（结构化流）。
- 若解析失败，检测是否为 SSE-style event names（chunk/paragraph/done），按 event 处理。
- 若都不是，检查内联分隔符（U+001E / <|PARA|>），按分隔符切分。
- 最后回退到启发式分段（基于 `\n\n`、句末标点或时间窗）。

2) 渲染策略
- 接收 `paragraph` 帧时，将该段作为单独的段落节点插入消息的段落数组，单独用 Markdown 渲染（每个段落一个 `ReactMarkdown` 渲染块），避免半截 Markdown 导致的短暂错位。
- 对于 `chunk` 帧，追加到当前正在生成的段落缓存并进行增量渲染（可直接渲染，也可按行缓冲以减少不完整 Markdown 影响）。
- 在收到 `done` 帧后，将剩余缓存段落标记为完成并触发最终渲染。

3) 容错与去重
- 使用 `seq` 字段保证帧按序处理；若检测到重复或跳序，按 `seq` 排序或请求重传/回退到拉取历史。

六、后端实现建议（服务端职责）

优先级：服务端尽量做帧封装；如果无法做到，则至少在 LLM 系统 prompt 中约定内联分隔符。

1) 在 LLM 流处理中包装帧
- 在读取模型流（token/partial）时，服务端负责：
  - 根据 token/语义边界切分 chunk；
  - 若发现模型输出内置段落 token（如 `<|PARA|>`），则发送 `paragraph` 帧含完整段落文本；
  - 否则以合理固定或动态长度发送 `chunk` 帧（并附 `seq`）。

2) 如果采用内联分隔符策略
- 在系统提示中约定一个 token（例如 `\u001E` 或 `<|PARA|>`）并让模型尽量在段落边界处输出它。示例系统提示片段：

  "请在每个段落边界处输出明确的分隔标记 `<|PARA|>`（不要将该标记放入代码块内部）。模型只需产生自然语言文本和该标记，后端会根据标记把流切分为段落。"

3) metadata 与 traceability
- 建议 `meta` 帧包含：`model`、`modelVersion`、`sourceChunkOffsets`（可选）与 `confidence`（可选），便于追踪与审计。

七、示例：服务端伪代码（Node/Express SSE）

```js
// 简化示例：将 LLM token stream -> SSE event
app.post('/api/v1/chat/stream', async (req, res) => {
  res.setHeader('Content-Type','text/event-stream')
  res.flushHeaders()
  const messageId = genId()
  let seq = 0

  const modelStream = await openLLMStream(req.body)
  for await (const token of modelStream){
    seq++
    const text = tokenToText(token)
    // detect in-band paragraph marker
    if(text.includes('<|PARA|>')){
      const parts = text.split('<|PARA|>')
      // send chunks and explicit paragraph frames accordingly
      for(const p of parts.slice(0,-1)){
        sendEvent(res,'paragraph', { protocolVersion:'1.0', type:'paragraph', messageId, paragraphId: genParaId(), seq: seq++, text:p, format:'markdown' })
      }
      // keep last part as ongoing chunk
      sendEvent(res,'chunk', { protocolVersion:'1.0', type:'chunk', messageId, seq, text: parts.at(-1), format:'markdown' })
    } else {
      sendEvent(res,'chunk', { protocolVersion:'1.0', type:'chunk', messageId, seq, text, format:'markdown' })
    }
  }
  sendEvent(res,'done',{ protocolVersion:'1.0', type:'done', messageId, seq: seq+1 })
})

function sendEvent(res, event, obj){
  res.write(`event: ${event}\n`)
  res.write(`data: ${JSON.stringify(obj)}\n\n`)
}
```

八、版本与兼容性
- 文档版本：V1；所有帧包含 `protocolVersion` 字段以便未来扩展。
- 客户端实现应具备回退逻辑：优先解析结构化帧 → 内联分隔符 → 启发式分段。

九、示例系统提示（供后端参考）

```
系统提示（示例）：
你是一个助手，请以 Markdown 格式输出回答。为了便于前端渲染，请在每个段落之间插入标记 <|PARA|> 作为段落边界（不要在代码块或表格内插入该标记）。示例输出：
<|PARA|>第一段文本内容。<|PARA|>第二段文本内容。
```

注意：模型可能不会 100% 遵守该约束，后端仍应以服务端封装为准。

十、交付物位置
- 本文档放置在：`deepresearch/docx/20260418-streaming-llm-output-protocol-v1.md`

十一、V1 后端实现约定（已落地）

为保证“方案1（结构化流）”可直接联调，后端当前实现采用以下固定约定：

1) 路由与传输
- 路由：`POST /api/v1/chat/stream`
- 传输：`text/event-stream`（SSE）
- SSE `event` 与帧内 `type` 保持一致：`chunk | paragraph | done | error`

2) 固定字段
- 所有帧均包含：`protocolVersion`、`type`、`messageId`、`seq`、`role`、`timestamp`
- `chunk`/`paragraph` 额外包含：`text`、`format`
- `paragraph` 额外包含：`paragraphId`
- `done` 包含：`meta.paragraphCount`

3) 段落边界策略
- 默认段落标记：`<|PARA|>`
- 后端会处理“标记跨 chunk”场景（例如 `<|PA` + `RA|>`），保证边界识别稳定。
- 每次识别到段落边界时，先输出已累计文本的 `paragraph` 帧，再继续后续流。
- 流结束时会自动 flush 最后一个未闭合段落，并输出 `done`。

4) 兼容性
- 当前实现仍会持续输出 `chunk` 帧用于增量渲染；`paragraph` 帧用于稳定段落落地。
- 前端建议采用“chunk 增量 + paragraph 定稿 + done 收尾”的处理策略。

如需我，我可以：
- 1) 将该协议生成可直接复制的后端实现示例（Python/FastAPI 或 Node/Express）；
- 2) 在前端 `streamChat` 中直接加入对该协议的解析/段落回调示例并提交 patch。请选择下一步。
