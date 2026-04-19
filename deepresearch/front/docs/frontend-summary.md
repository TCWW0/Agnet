# 前端项目阶段性总结 (deepresearch/front)

本文档用于以后对接后端、开发新功能和二次对话时作为上下文参考，概述当前前端实现、架构要点、样式/变量、关键组件、状态管理、弹窗/侧栏行为、测试与运行指令，以及与后端的对接建议。

---

## 一、项目概览
- 位置：`deepresearch/front`（工作区内单页 React 应用，TypeScript）
- 技术栈：React + TypeScript、Vite、Zustand（状态管理）、Vitest（单元测试）、原生 CSS（集中变量在 `theme.css`）
- 目的：仿照 ChatGPT 网页端的对话 UI，实现侧栏会话管理、右侧对话区、composer 自动扩展、popover 弹窗与折叠侧栏交互。

## 二、主要目录 & 关键文件
- 源码根：[deepresearch/front](deepresearch/front)
- 样式变量：[src/styles/theme.css](deepresearch/front/src/styles/theme.css)
- 全局样式与布局：[src/styles/index.css](deepresearch/front/src/styles/index.css)
- 状态管理：`useChatStore`（Zustand）：[src/store/chatStore.ts](deepresearch/front/src/store/chatStore.ts)
- 主要组件：
  - 侧栏： [src/components/Sidebar.tsx](deepresearch/front/src/components/Sidebar.tsx)
  - 弹窗（Portal）： [src/components/Popover.tsx](deepresearch/front/src/components/Popover.tsx)
  - 对话窗口： [src/components/ChatWindow.tsx](deepresearch/front/src/components/ChatWindow.tsx)
  - Composer（输入区）： [src/components/Composer.tsx](deepresearch/front/src/components/Composer.tsx)
  - 消息气泡： [src/components/Message.tsx](deepresearch/front/src/components/Message.tsx)
- 测试： [src/components/__tests__](deepresearch/front/src/components/__tests__)

## 三、架构要点（高层）
- 单页应用，UI 层负责渲染与交互，状态由 `useChatStore` 承载（消息数组、activeConversationId、常用操作）。
- 弹窗使用 React Portal（`Popover`），避免 host 经常 re-mount 导致输入框失去焦点；弹窗支持外部传入 `contentStyle` 以便精确定位。
- 布局的关键由 CSS 变量驱动，尤其是侧栏宽度：
  - 展开宽度：`--sidebar-width`（默认）
  - 折叠宽度：`--sidebar-collapsed-width`
  - 当前有效宽度：`--sidebar-current-width`（组件切换时通过 JS 更新，触发布局变更）
- 为避免折叠/展开时的闪烁，尽量使用 `transform`（GPU 合成层）做视觉缩放，而非直接改 `width/height`，并保证图标尺寸一致。

## 四、关键实现细节（逐项）

### 侧栏（`Sidebar.tsx`）
- 功能：新聊天、搜索、更多、最近会话列表、底部个人信息、折叠/展开。
- 折叠实现：点击折叠按钮或顶部图标会触发 `toggleCollapse()`，它在 `document.documentElement.style.setProperty('--sidebar-current-width', value)` 上设置当前宽度。
- 折叠效果：折叠态 DOM 会隐藏 `sessions`（最近列表）与 profile meta，仅保留图标按钮与 avatar；action 按钮切换为图标仅显示（label 隐藏）。
- 可访问性：顶部图标在折叠时被设置为可聚焦的 `role="button"`，支持 `Enter`/`Space` 触发展开。
- 搜索弹窗：内部使用 `draftQuery`（实时输入）与 `appliedQuery`（在 blur/Enter 时才应用）以避免在输入时改变侧栏主列表。

主要文件：[src/components/Sidebar.tsx](deepresearch/front/src/components/Sidebar.tsx)

### 弹窗（`Popover.tsx`）
- 使用 `createPortal` 渲染到根节点，组件仅挂载一次（避免依赖引起的反复挂载），通过 `contentStyle` 可传入 `left/top/width` 等定位样式。
- ESC/backdrop 支持关闭。

主要文件：[src/components/Popover.tsx](deepresearch/front/src/components/Popover.tsx)

### Composer（`Composer.tsx`）
- 固定在视口底部，宽度计算以 `--sidebar-current-width` 参与（居中对齐）。
- 文本区使用 `display:block` + CSS 限制 `min-height` / `max-height`，避免在 flex 父容器内用 JS 强行控制高度带来的问题。
- 发送按钮内嵌在 composer 控件区，`--composer-controls-width` 保证 textarea 右侧有预留空间。

主要文件：[src/components/Composer.tsx](deepresearch/front/src/components/Composer.tsx)

### ChatWindow / Message
- `ChatWindow` 负责消息列表渲染、自动滚动、空状态显示（受 `--empty-state-offset` 控制）。
- `Message` 组件负责单条消息气泡，气泡宽度受 `--bubble-max-ch` 控制（以 ch 估算字符宽度）。

主要文件： [src/components/ChatWindow.tsx](deepresearch/front/src/components/ChatWindow.tsx), [src/components/Message.tsx](deepresearch/front/src/components/Message.tsx)

## 五、样式变量说明（摘选）
定义位置：[src/styles/theme.css](deepresearch/front/src/styles/theme.css)
- `--sidebar-width`：侧栏展开宽度（默认）。
- `--sidebar-collapsed-width`：折叠宽度。
- `--sidebar-current-width`：当前实际生效宽度（JS 更新此变量以触发布局变化）。
- `--composer-min-width` / `--composer-max-width`：composer 宽度范围。
- `--composer-controls-width`：保留给控件（发送按钮）的宽度。
- `--chat-min-width`：聊天容器最小宽度。
- `--bubble-max-ch`：气泡最大字符数（ch）。
- `--sidebar-avatar-size` / `--sidebar-collapsed-avatar-size`：侧栏头像尺寸（可配置）。
- `--empty-state-offset`：空状态 Y 偏移。

在二次开发时优先通过这些变量调整布局/配色，而不是直接修改组件内联样式。

## 六、状态管理（Zustand）
文件： [src/store/chatStore.ts](deepresearch/front/src/store/chatStore.ts)

核心形态：
- `messages`: Array<{id, role: 'user'|'assistant', content: string}>
- `addMessage(msg)`：追加消息
- `appendToMessage(id, chunk)`：追加流式返回到某条消息
- `setMessages(msgs)`：直接设定当前消息数组（用于加载 mock 或切换会话）
- `activeConversationId` / `setActiveConversationId`

前端与后端对接时：优先把后端返回的消息格式映射到上面的形态，并在流式返回场景使用 `appendToMessage`。

## 七、后端对接建议（API / 协议示例）
推荐使用以 `/api/v1` 为前缀的 REST + POST 流式（ReadableStream）组合：

1) 获取会话列表
- GET /api/v1/conversations
- 返回：[{ id, title, updated_at }]

2) 新建会话
- POST /api/v1/conversations
- Body: { title?: string }
- 返回：{ id }

3) 获取会话消息
- GET /api/v1/conversations/:id/messages
- 返回：[{ id, role, content, created_at }]

4) 发送用户消息（并开始模型响应）
- POST /api/v1/chat
- Body: { conversationId?: string, messages: [{ role: 'user', content }] }
- 返回：{ message: { id, role, content } }（同步/一次性回复场景）

5) 流式响应（推荐）：
- POST /api/v1/chat/stream
- Body: { conversationId?: string, messages: [...] }
- Response: 使用 `Transfer-Encoding: chunked` 返回文本流（ReadableStream），每个数据帧为文本分片（或 newline-delimited JSON）。客户端使用 `fetch` + `ReadableStream` 读取并调用 `appendToMessage(messageId, chunk)` 逐步追加。

6) 追加消息（非流式）
- PATCH /api/v1/conversations/:id/messages/:messageId
- Body: { contentChunk }

注意事项：前端期望 message 对象至少包含 `id`, `role`, `content`；对于流式协议，建议后端在最后发送一个 JSON 完成标记（例如 `{ "messageId": "...", "done": true }`），以便客户端知道流已结束。

## 八、运行与开发（快速命令）
```bash
cd deepresearch/front
npm install
# 本地开发
npm run dev
# 单元测试
npm test
# 格式化 / lint 等（如项目含配置）
# npm run build
```

（若开发者环境差异较大，优先使用工作区已有的 dev script）

## 九、测试覆盖与注意点
- 当前单元测试位于 `src/components/__tests__`（Composer、Message 测试通过）。
- 建议补充：
  - Popover 焦点/挂载稳定性单元测试
  - Sidebar 折叠/展开行为的集成/端到端测试（Playwright 或 Cypress），重点测试折叠时的 DOM 行为和键盘可达性。

## 十、性能与可访问性建议
- 避免在折叠/展开时直接修改 layout 触发 reflow，优先 `transform` 动画（合成层）。
- Popover 挂载应尽量保持稳定（避免每次 props 变更时卸载重挂），以保留输入焦点与选中状态。
- 为图标与按钮提供 `aria-label`、`role`、键盘事件支持，并确保焦点样式可见。

## 十一、常见改动点与扩展点
- 将 `--sidebar-current-width` 的读写集中到一个 helper（例如 `src/utils/layout.ts`），便于不同组件统一管理与测试。
- 若引入 i18n，请把中文文本提取到资源文件，组件使用 key 渲染。
- 增加 `E2E` 测试覆盖折叠/展开、搜索弹窗交互、流式消息追加。

## 十二、联系人与下一步建议
- 我已把本文件保存为： [docs/frontend-summary.md](deepresearch/front/docs/frontend-summary.md)
- 建议下一步：
  1. 根据后端能力确定是否使用 WebSocket 或 SSE 进行流式返回。
  2. 由后端提供一个最小可工作的会话 API（见上方示例），前端可先对接 mock 后端再切换真实实现。
  3. 添加 E2E 用例覆盖折叠/展开与弹窗焦点行为。

---

如需我把上面的 API 示例写成 OpenAPI (YAML/JSON) 文档，或生成用于后端对接的示例请求代码（fetch/axios），我可以接着生成。