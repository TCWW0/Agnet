---
name: deepresearch-integration-guardrails
description: Guardrails for deepresearch fullstack implementation. Use this skill whenever the user asks to build or modify deepresearch backend/frontend integration, API design, or phased documentation. Enforce backend code placement under deepresearch/backend, prevent accidental edits in frame unless explicitly requested, and place stage docs into backend/docx or deepresearch/docx based on audience.
---

# DeepResearch Integration Guardrails

用于约束 deepresearch 项目的前后端联调开发过程，确保目录边界和文档沉淀策略稳定执行。

## When to use

当用户出现以下语义时，必须使用本技能：

- 在 deepresearch 下搭建后端服务、接口或 API
- 让前端对接后端进行联调
- 需要阶段性总结文档
- 同时提到 frame 与 deepresearch，且要求避免污染 frame

## Core constraints

1. 后端实现目录限制
- 后端可执行代码、配置、测试均放在 deepresearch/backend 下。
- 未经用户明确同意，不修改 frame 目录结构与代码。

2. API 前缀约定
- 所有 public API 在项目中必须使用统一前缀 `/api/v1`，后端路由、文档与前端调用均应遵守此约定。

3. 文档落位限制
- 后端强相关阶段文档：deepresearch/backend/docx
- 前后端共享文档：deepresearch/docx

4. 文件膨胀与拆分规则
- 当单个源文件行数超过 1500 行（约 1.5k 行）时，必须在提交合并前进行一次文件结构 review。Review 内容应包括：
	- 是否将功能拆分成更小的模块或类
	- 是否将路由/控制器与业务逻辑分离
	- 是否需要将公共类型/模型提取到 `schemas` 或 `models` 包
	- 若拆分方案不明确，必须征询用户确认后再合并

5. 启动脚本约定
- 在 `deepresearch/backend` 与 `deepresearch/front` 下各保留一个启动脚本，用以本地开发时快速启动服务（例如 `start.sh` 或 `run.sh`）。
- 本次实现会在 `deepresearch/backend` 下添加一个后端启动脚本供本地开发使用；前端脚本可在后续步骤中添加。

6. Import 放置约束
- 所有模块级别的 `import` 应尽量在文件顶部集中声明，以提高可读性与维护性。只在确有必要（例如为避免循环依赖、或减少冷启动时的资源占用）时使用延迟导入（函数/方法内部导入），并在代码中添加注释说明原因。项目中新增文件必须遵守此规范。

7. 最小可用目标（MVP）
- 前端可发起请求
- 后端可处理请求
- 后端可返回可展示响应

8. 角色要求
- 如果用户在聊天中提到你是后端开发者或者前端开发者，你必须严格限制自己的修改范围。就比如如果是一个前端开发者的角色，你只能修改 deepresearch/front 目录下的代码，不能修改 deepresearch/backend 目录下的代码；如果是一个后端开发者的角色，你只能修改 deepresearch/backend 目录下的代码，不能修改 deepresearch/front 目录下的代码。

9. 代码质量要求
- 所有新增代码必须符合项目的代码风格和质量标准，包括但不限于：
  - 使用类型注解
  - 在代码生成完之后对于文件进行静态检查，处理可能存在的静态检查错误
  - 在提交前运行现有的测试套件，确保没有引入新的错误
  - 对于新增的功能，编写相应的单元测试或集成测试，确保功能的正确性和稳定性
## Default workflow

1. 读取上下文
- 先读 deepresearch/front/docs/frontend-summary.md
- 再读 frame/core 的关键文件（至少：base_llm, openai_adapter, llm_orchestrator, message）

2. 定义契约
- 优先对齐前端已有接口路径
- 在后端定义明确的请求/响应模型

3. 搭建后端
- 创建最小 HTTP 服务（建议 FastAPI）
- 先提供 mock 可用链路，再支持切换真实 frame 能力

4. 记录阶段结果
- 每完成一个关键阶段，输出阶段总结文档
- 文档要写明：已完成、未完成、风险、下一步

## Output checklist

交付前逐项检查：

- [ ] 后端代码仅在 deepresearch/backend
- [ ] frame 未被修改（除非用户明确要求）
- [ ] 至少一个可联调 API 可用
- [ ] 阶段文档已放入正确目录
- [ ] 运行验证已完成（最小 smoke test）

## Example triggers

- "在 deepresearch 下做一个可联调的聊天后端"
- "先别动 frame，先把 backend 搭好"
- "请把阶段总结文档分别输出到 backend/docx 和 deepresearch/docx"
