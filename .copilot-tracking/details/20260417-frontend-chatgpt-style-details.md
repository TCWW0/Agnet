<!-- markdownlint-disable-file -->

# Task Details: Frontend — ChatGPT 风格对话界面

## Research Reference

**Source Research**: #file:../research/20260417-frontend-chatgpt-style-research.md

## Phase 1: 基础骨架与静态布局

### Task 1.1: Scaffold 项目并实现基础布局

实现内容：

- 使用 Vite + React + TypeScript + Tailwind 初始化项目；
- 实现页面主布局：左侧 `Sidebar`，右侧 `ChatWindow`，底部 `Composer`；
- 使用本地 mock 数据驱动消息渲染，保证交互链路可测试。

- **Files**:
  - front/package.json - 项目依赖与脚本
  - front/src/main.tsx - 应用入口
  - front/src/App.tsx - 根布局
  - front/src/pages/ChatPage.tsx - 聊天页面容器
  - front/src/components/Sidebar.tsx - 侧边栏
  - front/src/components/ChatWindow.tsx - 消息列表容器
  - front/src/components/Message.tsx - 消息渲染
  - front/src/components/Composer.tsx - 输入栏
  - tailwind.config.cjs, postcss.config.cjs - 样式工具配置

- **Success**:
  - 页面布局与 ChatGPT 风格一致（白色主题、左侧栏、对话区、输入栏）；
  - Composer 能发送 mock 消息并在 ChatWindow 中展示；
  - 组件职责清晰、可单元测试。

- **Research References**:
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 43-67) - 项目结构建议
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 77-125) - App 布局与 Composer 示例
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 221-226) - Phase 1 建议

## Phase 2: Agent 集成与流式消息

### Task 2.1: 接入 Agent 后端，支持流式渲染

实现内容：

- 在 `services/` 中实现 `agentClient.ts` 与 `api.ts`，支持 POST 请求与 SSE/WS/Fetch-Stream 三种接入方式；
- 将流式输出逐步写入 store 并在 Message 组件中增量渲染；
- 提供回退方案（当后端不支持流式时使用一次性响应）。

- **Files**:
  - front/src/services/api.ts - HTTP helpers + fetch-stream 实现
  - front/src/services/agentClient.ts - SSE/WS 客户端封装
  - front/src/store/chatStore.ts - 支持增量消息写入（zustand）
  - tests/agent-integration.test.ts - 流式集成测试（mock 后端）

- **Success**:
  - 能够与后端建立流式连接并逐步渲染 token；
  - 当网络异常或后端不支持流式时具备健壮的降级策略；

- **Research References**:
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 131-166) - 消息流式传输示例（SSE/WS/fetch-stream）
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 168-183) - API 约定示例
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 228-231) - Phase 2 建议

## Phase 3: 样式打磨、可访问性与测试

### Task 3.1: UI 细节与测试覆盖

实现内容：

- 使用 Tailwind 与 CSS 变量细化消息气泡、悬浮、滚动动画；
- 实现键盘交互（Enter 发送、Shift+Enter 换行）、焦点管理与 aria 属性；
- 添加单元测试、组件快照与 E2E 测试覆盖主要对话场景。

- **Files**:
  - front/src/styles/index.css - 全局样式与 CSS 变量
  - test/components/ - 组件单元测试
  - playwright/ - E2E 测试配置与用例

- **Success**:
  - 视觉/交互与可访问性要求通过手动/自动检查；
  - CI 中通过 lint/test/build 检查；

- **Research References**:
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 204-213) - 样式与主题、可访问性建议
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 215-219) - 测试与 CI 建议
  - #file:../research/20260417-frontend-chatgpt-style-research.md (Lines 233-235) - Phase 3 建议

## 依赖项与前提

- Node.js >= 18, npm/yarn/pnpm；
- 推荐使用 `pnpm` 或 `npm` 做包管理；
- 若使用后端流式接口，需协调后端 SSE/WS/Chunked HTTP API。

## 验收标准（Task-level）

- Phase 1：静态 UI 与 mock 数据交互完整，组件分离并有基本单元测试；
- Phase 2：流式消息可以端到端展示（至少在 mock 后端下），UI 支持增量渲染；
- Phase 3：样式完成、响应式和可访问性通过，主要测试在 CI 中通过。
