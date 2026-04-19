---
applyTo: '.copilot-tracking/changes/20260418-agent-frontend-integration-changes.md'
---

<!-- markdownlint-disable-file -->

# Task Checklist: Agent 前后端联调（第一版）

## Overview

在现有 `frame` Agent 框架与 `deepresearch/front` 前端基础上，实现第一版联调能力：前端能发送消息到后端并收到 assistant 的响应（支持同步与流式）。

## Objectives

- 在本地快速搭建后端 HTTP 接口（POST /api/chat, POST /api/chat/stream）。
- 提供可切换的 LLM 实现（MockLLM / BaseLLM），便于无 Key 联调与生产切换。
- 前端调用接口并在 UI 中正确展示 assistant 返回。

## Research Summary

### Project Files

- deepresearch/front - 前端单页应用（React + TS），包含 `Composer`、`ChatWindow`、`useChatStore` 等（用于 UI 集成）。
- frame/core - Agent 框架核心：`BaseAgent`、`BaseLLM`、`OpenAIResponsesAdapter`、`LLMInvocationOrchestrator` 等。

### External References

- #file:../research/20260417-frontend-chatgpt-style-research.md - 前端实现、流式传输与 API 约定的研究总结

## Implementation Checklist

### [ ] Phase 1: API 与数据契约

- [ ] Task 1.1: 定义 HTTP API（请求/响应格式）

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 11-25)

- [ ] Task 1.2: 定义 JSON ↔ `frame.core.message.Message` 映射

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 26-31)

### [ ] Phase 2: 后端实现

- [ ] Task 2.1: 创建 FastAPI 服务入口与路由

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 34-39)

- [ ] Task 2.2: 实现 `MockLLM` 用于本地调试

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 40-57)

- [ ] Task 2.3: 封装 Agent 初始化与 HTTP handlers

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 58-69)

### [ ] Phase 3: 前端对接

- [ ] Task 3.1: 前端服务层实现 `sendMessage` / `sendMessageStream`

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 72-88)

- [ ] Task 3.2: Composer 调用 API 并写入 `useChatStore`

  - Details: .copilot-tracking/details/20260418-agent-frontend-integration-details.md (Lines 89-92)

## Dependencies

- Backend: FastAPI, uvicorn
- Frontend: deepresearch/front 的现有依赖（Vite, React, zustand）

## Success Criteria

- 前端能发送一条消息并收到 assistant 的回复并正确展示。
- 流式接口能增量更新消息（可选首版留为同步）。
