<!-- markdownlint-disable-file -->
# 前端研究：ChatGPT 风格对话界面（2026-04-17）

## 概述

本研究文档汇总了为 Agent 项目实现一个类 ChatGPT 网页端对话界面（白色主题、左侧侧边栏、右侧对话区、输入栏）的最佳实践与实现参考，面向后续分阶段实现和迭代。

## 目标

- 构建一个可扩展的前端框架，用于展示 Agent 对话与交互；
- 确保架构优雅、组件化、易于扩展与测试；
- 初始实现侧重 UI 布局、可插拔的数据/消息层（REST/流式/WS 接口）、基本样式；后续逐步接入复杂 Agent 流程与持久化。

## 推荐技术栈（理由）

- React 18 + TypeScript：组件化、类型安全、社区生态丰富；
- Vite：快速的本地开发体验与构建速度；
- Tailwind CSS：快速样式迭代与一致性，便于复刻 ChatGPT 风格；
- 状态管理：`zustand`（轻量）或 `redux-toolkit`（大型项目）；
- 流式/实时：优先使用 SSE（EventSource）或 WebSocket，fetch+ReadableStream 作为备用；
- 测试：Vitest + React Testing Library + Playwright（端到端）。

## 开发环境与工具（命令）

推荐开发流程：

```
# 初始化（示例）
npm create vite@latest front -- --template react-ts
cd front
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npm install zustand

# 启动
npm run dev

# 测试
npm run test
```

## 项目结构建议

```
front/
├─ package.json
├─ index.html
├─ src/
│  ├─ main.tsx
│  ├─ App.tsx
│  ├─ pages/
│  │  └─ ChatPage.tsx
│  ├─ components/
│  │  ├─ Sidebar.tsx
│  │  ├─ ChatWindow.tsx
│  │  ├─ Message.tsx
│  │  └─ Composer.tsx
│  ├─ services/
│  │  ├─ api.ts           # REST + streaming helpers
│  │  └─ agentClient.ts   # WebSocket/SSE client
│  ├─ store/
│  │  └─ chatStore.ts     # zustand store
│  └─ styles/
│     └─ index.css
└─ vite.config.ts
```

## 组件划分与职责

- `Sidebar`：展示会话列表、操作按钮（新建会话、导入/导出等）；
- `ChatWindow`：消息列表容器，负责滚动、分组和时间戳；
- `Message`：单条消息渲染，支持富文本、代码块、附件；
- `Composer`（输入栏）：文本输入、多行、回车发送、快捷按钮；
- `App` / `ChatPage`：页面级容器，初始化 store，与 agent 后端连接。

### App 布局示例（Tailwind + React）

```tsx
// src/App.tsx
import React from 'react'
import Sidebar from './components/Sidebar'
import ChatPage from './pages/ChatPage'

export default function App(){
  return (
    <div className="h-screen flex bg-white">
      <aside className="w-72 border-r">
        <Sidebar />
      </aside>
      <main className="flex-1">
        <ChatPage />
      </main>
    </div>
  )
}
```

### Composer 示例

```tsx
// src/components/Composer.tsx
import React, { useState } from 'react'

export default function Composer({ onSend }: { onSend: (text: string) => void }){
  const [text, setText] = useState('')
  return (
    <div className="p-4 border-t bg-gray-50">
      <textarea
        className="w-full rounded-md p-2 border"
        value={text}
        onChange={e => setText(e.target.value)}
        rows={2}
        placeholder="请输入消息..."
      />
      <div className="text-right mt-2">
        <button
          className="bg-blue-600 text-white px-4 py-1 rounded"
          onClick={() => { onSend(text); setText('') }}
        >发送</button>
      </div>
    </div>
  )
}
```

## 消息流式传输（示例）

三种常见方式：SSE（EventSource）、WebSocket、fetch+ReadableStream（流式响应）。

### 1) SSE（服务器推送）

```js
// 客户端
const es = new EventSource('/api/chat/stream?conversationId=123')
es.onmessage = (e) => {
  // 服务器按 token/段推送字符串
  console.log('chunk', e.data)
}
es.onerror = (err) => { console.error(err) }
```

### 2) WebSocket

```js
const ws = new WebSocket('wss://example.com/ws')
ws.onopen = () => ws.send(JSON.stringify({ type: 'start', messages }))
ws.onmessage = (ev) => { const msg = JSON.parse(ev.data); /* handle token */ }
```

### 3) fetch + ReadableStream（推荐用于 HTTP 流式响应）

```js
const resp = await fetch('/api/chat', { method: 'POST', body: JSON.stringify({ messages }) })
const reader = resp.body.getReader()
const decoder = new TextDecoder()
let done = false
while(!done){
  const { value, done: d } = await reader.read()
  done = d
  if(value){
    const chunk = decoder.decode(value)
    // 解析 chunk 并逐步渲染
  }
}
```

## API 约定（示例）

- POST `/api/chat` -> 发起一次对话生成（同步/一次性响应）
- POST `/api/chat/stream` -> 返回 stream（SSE 或 chunked HTTP）
- WS `/ws` -> 建立持久连接进行流式 token 下发

示例请求体（JSON）：

```json
{
  "conversationId": "optional",
  "messages": [{"role":"user","content":"你好"}],
  "model": "gpt-like-agent",
  "meta": { }
}
```

## 状态管理示例（zustand）

```ts
// src/store/chatStore.ts
import create from 'zustand'

type Message = { id: string; role: 'user'|'assistant'; content: string }

type ChatState = {
  messages: Message[]
  addMessage: (m: Message) => void
}

export const useChatStore = create<ChatState>(set => ({
  messages: [],
  addMessage: (m) => set(s => ({ messages: [...s.messages, m] }))
}))
```

## 样式与主题

- 使用 Tailwind 进行全局布局和快速迭代；重要的全局样式控制（最大宽度、气泡样式、颜色变量等）可在 `styles/index.css` 中定义；
- 主题色（白色主色调）可通过 Tailwind 配置与 CSS 变量实现，方便日后切换深色模式。

## 可访问性与响应式

- 键盘可达性：支持 Enter 发送，Shift+Enter 换行；
- 可读性：信息层次清晰，足够的对比度；
- 响应式：在移动端侧边栏折叠为抽屉或隐藏，仅保留对话区。

## 测试与 CI 建议

- 单元/组件测试：Vitest + React Testing Library；
- E2E：Playwright（覆盖主要对话场景与流式渲染）；
- CI：在 push 时运行 lint、测试与构建。

## 实施分阶段建议（参考优先级）

- Phase 1（基础骨架，1-2 天）
  - Scaffold 项目（Vite + React + TS + Tailwind）
  - 实现静态布局：`Sidebar`、`ChatWindow`、`Composer`，本地假数据渲染
  - 提供 mock 服务或本地静态数据

- Phase 2（Agent 集成，2-4 天）
  - 增加后端代理/接口契约（或使用现有 Agent 后端）
  - 实现流式消息渲染（SSE 或 fetch-stream）
  - 引入简单状态管理（zustand）

- Phase 3（样式、可访问性、测试，2-3 天）
  - 精细化样式与交互（动画、滚动控制、消息分组）
  - 添加测试与 CI，优化性能与包体积

## 风险与权衡

- 流式渲染实现与后端协作成本较高（需要后端支持分块或 WS）；
- 若未来需要 SSR 或 SEO，可能选 Next.js 而非 Vite；此处优先以开发速度为主，后续可迁移。

## 外部参考

- Vite: https://vitejs.dev/
- Tailwind: https://tailwindcss.com/
- React: https://reactjs.org/
- OpenAI API 文档（示例）: https://platform.openai.com/docs
- ChatGPT 网页端风格参考: https://chat.openai.com/

## 实施建议总结

初期优先完成 Phase 1：搭建清晰的组件化布局与样式、并提供可替换的消息层（mock vs 实际 agent），保证架构优雅、组件职责单一。随后按 Phase 2/3 逐步接入流式 agent、完善交互与测试。
