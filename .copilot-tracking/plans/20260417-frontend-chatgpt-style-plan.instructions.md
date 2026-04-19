---
applyTo: ".copilot-tracking/changes/20260417-frontend-chatgpt-style-changes.md"
---

<!-- markdownlint-disable-file -->

# Task Checklist: Frontend — ChatGPT 风格对话界面

## Overview

实现一个类 ChatGPT 的网页版对话页面（白色主题、左侧侧边栏、右侧对话区、输入栏），作为 Agent 项目的前端基础框架，以便后续迭代 Agent 功能。

## Objectives

- 搭建可扩展的前端骨架并实现静态 UI 布局；
- 支持流式消息渲染与后端 Agent 集成；
- 提供测试覆盖与可访问性保证，便于后续迭代。

## Research Summary

### Project Files

- front/ - 前端项目根目录，包含 `src/`、`package.json`、`vite.config.ts` 等（见研究文档项目结构）。

### External References

- #file:../research/20260417-frontend-chatgpt-style-research.md - 前端研究与代码示例
- #fetch:https://vitejs.dev/ - Vite 文档
- #fetch:https://tailwindcss.com/ - Tailwind 文档

## Implementation Checklist

### [ ] Phase 1: Scaffold & Static Layout

- [ ] Task 1.1: Scaffold 项目并实现基础布局

  - Details: .copilot-tracking/details/20260417-frontend-chatgpt-style-details.md (Lines 9-38)

### [ ] Phase 2: Agent Integration & Streaming

- [ ] Task 2.1: 接入 Agent 后端，支持流式渲染
  - Details: .copilot-tracking/details/20260417-frontend-chatgpt-style-details.md (Lines 40-63)

### [ ] Phase 3: Styling, Accessibility & Tests

- [ ] Task 3.1: UI 细节与测试覆盖
  - Details: .copilot-tracking/details/20260417-frontend-chatgpt-style-details.md (Lines 65-87)

## Dependencies

- Node.js >= 18
- npm / pnpm
- Vite, Tailwind CSS
- 后端 Agent API（支持流式或一次性响应）

## Success Criteria

- 静态 UI 布局完成并可在本地运行；
- 流式消息能端到端显示（至少在 mock 后端上）；
- 主要交互与可访问性测试通过，CI 能够运行 lint/test/build。
