<!-- markdownlint-disable-file -->

# Task Research Notes: Frontend Markdown Streaming Rendering

## Research Executed

### File Analysis

- deepresearch/front/src/components/Message.tsx
  - `rawParagraphs` 在 `paragraphs` 为空时先从 `content` 解析，再无条件 push `partial`，导致同一段流式文本双份渲染。
- deepresearch/front/src/store/chatStore.ts
  - `appendPartial` 同时维护 `partial` 与拼接后的 `content`，且在无段落时会生成前缀 `\n\n`，放大了渲染层重复与空白观感问题。
- deepresearch/front/src/pages/ChatPage.tsx
  - `streamChat` 的 `chunk` 和 `paragraph` 回调并行写入状态；当前 UI 逻辑未对“同源内容不同帧类型”做单一渲染源约束。
- deepresearch/front/src/services/agentClient.ts
  - 解析器会分别回调 `onChunk` 与 `onParagraph`，与后端协议一致；问题在前端状态消费层而非流解析器本身。
- deepresearch/backend/src/stream_framing.py
  - 后端在段落标记命中时先发 `chunk`（before marker）再发 `paragraph`（累计段落），语义上要求前端有“增量态 + 定稿态”的去重策略。
- deepresearch/front/src/styles/index.css
  - `.bubble` 统一使用 `white-space: pre-wrap`，会对 Markdown 块级元素间换行/空白文本节点进行保留，造成额外空白行体感。

### Code Search Results

- partial|appendPartial|pushParagraph|finalizeMessage|streaming
  - 命中 `Message.tsx`、`ChatPage.tsx`、`chatStore.ts`，确认重复问题发生在“状态组织 + 视图拼装”而不是单点网络解析。
- react-markdown|remark|rehype|markdown
  - 命中 `Message.tsx`，确认 Markdown 渲染统一走 `ReactMarkdown + remark-gfm + rehype-sanitize`。
- StrictMode|React.StrictMode
  - 仅命中 `main.tsx`，结合 React 官方说明可排除“事件处理被双调用”导致的本问题主因。

### External Research

- #githubRepo:"remarkjs/react-markdown README line endings and block output"
  - 官方示例与测试表明 Markdown 会输出标准块级结构（`<p>`, `<ul>`, `<ol>` 等），并强调 JSX/行结尾空白处理差异，支持“避免在外层统一 pre-wrap”结论。
- #githubRepo:"vercel/ai repeated assistant messages streaming dedup"
  - AI SDK 文档存在“Repeated assistant messages”排障条目，建议在流式消费侧避免重复拼接，支持“单一真值渲染源”策略。
- #fetch:https://developer.mozilla.org/en-US/docs/Web/CSS/white-space
  - `pre-wrap` 会保留空白与换行，适用于原始文本但容易放大块级 Markdown 邻接空白。
- #fetch:https://react.dev/reference/react/StrictMode
  - StrictMode 额外重渲染主要针对组件纯度与 effect，不包含事件处理器双调用，辅助排除误判路径。
- #fetch:https://developer.mozilla.org/en-US/docs/Web/CSS/position
  - `position: fixed` 元素脱离文档流并建立 stacking context，滚动容器与覆盖层需显式分层。
- #fetch:https://developer.mozilla.org/en-US/docs/Web/CSS/overflow
  - 需为滚动容器提供明确高度与 overflow 策略，才能把可滚动区域限制在输入栏上方。
- #fetch:https://developer.mozilla.org/en-US/docs/Web/CSS/z-index
  - 覆盖层与输入栏需要清晰 z-index 层级，防止消息内容“穿透到输入栏下方区域”。

### Project Conventions

- Standards referenced: `deepresearch/front` 采用 React + TypeScript + Vite + Zustand；样式集中在 `src/styles/theme.css` 和 `src/styles/index.css`；流式协议采用 `chunk/paragraph/done`。
- Instructions followed: 仅调研与文档更新，不修改业务源码；依据 `deepresearch/docx/20260418-streaming-llm-output-protocol-v1.md` 对齐前后端语义。

## Key Discoveries

### Project Structure

- 右侧主链路：`App -> ChatPage -> ChatWindow -> Message`，输入区 `Composer` 为固定定位悬浮层。
- 流式状态在 Zustand 中维护：`paragraphs`（已定稿）、`partial`（增量中）、`content`（兼容字段）。
- 后端分帧器会发送两类文本帧：`chunk`（增量）与 `paragraph`（定稿），并在 `done` 收尾。

### Implementation Patterns

1) 重复渲染根因（已可执行复现）
- `Message.tsx` 当前逻辑：
  - `paragraphs` 为空时：`rawParagraphs = parseParagraphs(content)`。
  - 同时又执行：`rawParagraphs.push(partial)`。
- `appendPartial` 又把 `partial` 拼进 `content`，因此同一流式文本在同一帧会进入两条渲染路径。
- 最小复现实验输出：`["hello","hello"]`（长度为 2），证明重复渲染来自前端拼装逻辑。

2) 段落/列表出现额外空白行
- 直接原因一：上述双份段落渲染在视觉上表现为“起始和续写间多一行”。
- 直接原因二：`.bubble { white-space: pre-wrap; }` 作用在 Markdown 容器外层，会保留块间换行与空白文本节点，进一步放大空白感（尤其是列表和段落交界）。

3) 输入栏下方应不透明且不可被消息渲染“穿透”
- 当前实现中 `Composer` 是 fixed 浮层，`ChatWindow` 通过大 `padding-bottom` 避免遮挡，但消息仍属于整块滚动内容的一部分。
- 结果是消息可继续滚入输入栏下方区域（只是被浮层盖住），不满足“输入栏上边界以下区域为不透明隔离区”的产品预期。

### Complete Examples

```tsx
// Source: deepresearch/front/src/components/Message.tsx + chatStore.ts
// Current behavior (causes duplicate rendering during streaming when paragraphs is empty)
const rawParagraphs: string[] = shouldShowLoading
  ? []
  : (message.paragraphs && message.paragraphs.length
      ? message.paragraphs
      : parseParagraphs(message.content || ''))

if (!shouldShowLoading && message.partial && message.partial.trim()) {
  rawParagraphs.push(message.partial)
}

// Store side
const partial = (m.partial || '') + chunk
const content = (m.paragraphs || []).join('\n\n') + (partial ? '\n\n' + partial : '')
return { ...m, partial, content }
```

### API and Schema Documentation

- 已落地协议（V1）字段：`protocolVersion`, `type`, `messageId`, `seq`, `role`, `timestamp`。
- 帧语义：
  - `chunk`: 增量文本。
  - `paragraph`: 完整段落定稿文本。
  - `done`: 消息完成，含统计元数据。
- 后端行为要点：命中段落标记时会“先 chunk 后 paragraph”，前端必须以状态机方式消费而非简单字符串累加。

### Configuration Examples

```css
/* Source: deepresearch/front/src/styles/index.css (current) */
.bubble {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.composer {
  position: fixed;
  z-index: 40;
}

.content-wrap {
  overflow: auto;
}
```

### Technical Requirements

- 必须保证流式阶段“单一可视文本来源”，禁止同一段同时由 `content` 和 `partial` 双路渲染。
- Markdown 块级元素渲染区域应采用 `white-space: normal`（或仅在纯文本场景启用 `pre-wrap`）。
- 右侧区域需要“滚动容器上限 + 固定不透明遮罩 + Composer 高层级”三件套，确保输入栏上边界以下不显示消息内容。
- 方案需兼容现有 `chunk/paragraph/done` 协议，不改变后端契约。

## Recommended Approach

采用“前端单一状态机渲染方案”（唯一推荐）：

1. 消息文本单一真值
- 流式中仅用 `partial` 展示增量。
- `paragraph` 到达时写入 `paragraphs` 并清空 `partial`。
- `content` 仅作为兼容/持久化字段，不参与流式 UI 主渲染决策。

2. 修复重复渲染点
- 在 `Message` 中改为互斥策略：
  - `paragraphs.length > 0` 时渲染 `paragraphs + partial(可选)`；
  - `paragraphs.length === 0` 时仅渲染 `partial`（或历史回放时渲染 parse(content)）。
- 避免同一时刻同时 `parse(content)` 与 `push(partial)`。

3. 修复空白行与列表空隙
- 将 Markdown 气泡容器的 `white-space` 从 `pre-wrap` 下沉为按角色/内容类型控制：
  - Assistant Markdown 容器使用 `white-space: normal`。
  - 如需保留用户手动换行，仅对用户纯文本气泡启用 `pre-wrap`。

4. 实现输入栏下方不透明隔离区
- 新增右侧滚动区结构：`chat-scroll`（可滚动）+ `composer-occluder`（固定不透明遮罩）。
- `chat-scroll` 高度设为 `calc(100vh - topNav - composerReserved)`，限制消息只在输入栏上方滚动。
- `composer-occluder` 与 `composer` 使用明确 z-index 分层：`chat < occluder < composer`。

该方案可一次性解决：重复渲染、空白行异常、输入栏下方穿透显示。

## Implementation Guidance

- **Objectives**: 消除流式重复渲染；稳定 Markdown 段落/列表排版；将可滚动渲染区域严格限制在输入栏上边界以上。
- **Key Tasks**: 重构 `Message` 的 rawParagraphs 计算互斥逻辑；调整 `chatStore.appendPartial` 的 content 拼接；重构右侧滚动与遮罩层级 CSS/DOM。
- **Dependencies**: 现有 `react-markdown` + `remark-gfm` + `rehype-sanitize`；后端 V1 分帧协议；当前 CSS 变量（`--top-nav-height`, `--composer-*`）。
- **Success Criteria**: 流式期间同一文本仅渲染一次；段落/列表无额外空白行；输入栏上边界以下区域完全不显示消息内容且保持不透明。