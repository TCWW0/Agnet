<!-- markdownlint-disable-file -->

# Task Research Notes: Code Agent 落地方案研究

## Research Executed

### File Analysis

- frame/agents/code_agent.py
  - `CodeAgent` 目前只是 `BaseAgent` 的空壳，只做了继承和构造转发，没有独立行为、工具编排或验证回路。
- frame/agents/simple_agent.py
  - 这是最轻量的 `BaseAgent` 使用范式，说明当前框架允许“只定 prompt + LLM 调用 + commit turn”的最小 agent。
- frame/agents/react_agent.py
  - 已经存在工具注册、流式输出和自动工具执行的完整实现，是最接近“可扩展专项 agent”的参考样板。
- frame/agents/tool_aware_agent.py
  - 与 `ReactAgent` 一样复用了 `BaseAgent -> BaseLLM -> ToolRegistry` 结构，证明“新 agent 主要靠工具集合和提示词分化”是当前主路径。
- frame/core/base_agent.py
  - 负责会话、历史消息、记忆钩子和 turn commit，是所有 agent 的通用控制面。
- frame/core/base_llm.py
  - 已经封装了流式与非流式调用、工具模式选择、最大轮次和回调，是代码 agent 复用的核心调用层。
- frame/core/llm_orchestrator.py
  - 现成的多轮 tool call 状态机已经具备“模型调用工具 -> 执行 -> 回传 -> 再调用”的闭环。
- frame/tool/base.py
  - `BaseTool` / `ToolDesc` / `ToolResponse` 已经定义了工具 schema、参数校验和输出结构，是代码操作工具的自然扩展点。
- frame/tool/register.py
  - 工具注册器很薄，当前没有 namespace 或隔离能力，意味着代码 agent 要靠更细的工具设计来控制暴露面。
- frame/evaluation/harness.py
  - 已有 `EvalExecutor` + dataset 驱动的评测框架，适合把 code agent 质量锚定到客观用例上。
- frame/evaluation/metrics.py
  - 已有 `pass_at_k`、`recall_at_k`、`precision_at_k` 等指标，说明框架已经具备“把 agent 质量数值化”的基础。
- frame/evaluation/memory/README.md
  - 评测结果会写出 `report.json` 和 `summary.txt`，说明项目已经有稳定的离线评测产物约定。
- frame/evaluation/docx/README.md
  - 评测文档索引强调通过 runner 和 JSONL 用例持续迭代 grader，这个流程可以直接迁移到 code agent 评测。
- .github/instructions/ 与 copilot/
  - 本 workspace 中未发现匹配文件；当前可用的项目约束主要来自 `project-learn` 与仓库现有代码。

### Code Search Results

- class CodeAgent|CodeAgent(
  - 仅命中 `frame/agents/code_agent.py`，确认没有其他实现分支在决定它的行为。
- subprocess|pytest|unittest|run_test|exec(
  - `frame` 目录内没有现成的代码执行、补丁应用或测试运行工具，只有测试文件里引用了 `pytest`。
- BaseAgent|ToolAwareAgent|SimpleAgent|ReactAgent
  - 说明当前框架里 agent 的差异主要来自工具集、prompt 和 turn 处理，而不是新的基础架构。
- tool|registry|register_tool|BaseTool
  - 确认工具体系是框架预留的正式扩展口，适合作为 code agent 的行为边界。

### External Research

- #fetch:https://www.anthropic.com/engineering/building-effective-agents
  - Anthropic 把 coding agent 的优势归因于“代码可被自动测试验证”，并强调从简单、可组合的 workflow 开始，只有在确有收益时再增加 agent 复杂度。
  - 他们还明确建议把工具设计成清晰、可测试、可解释的接口，并在 sandbox 中做充分验证。
- #fetch:https://developers.openai.com/api/docs/guides/function-calling
  - 官方工具调用流程是明确的五步闭环：请求模型、收到 tool call、应用侧执行、带着 tool output 再请求模型、得到最终结果或更多 tool call。
  - strict mode 需要 `additionalProperties: false` 且所有字段都 required，这对代码 agent 的工具 schema 尤其重要。
  - 官方建议保持初始工具集尽量小，并用清晰的函数名、参数描述和示例减少调用错误。
- #fetch:https://developers.openai.com/api/docs/guides/evals
  - eval 需要先定义任务，再提供 `data_source_config` 和 `testing_criteria`，然后用数据集驱动运行和分析结果。
  - 官方将这个流程类比为 BDD，适合把 code agent 的迭代质量固定在可复现测试上。
- #fetch:https://developers.openai.com/api/docs/guides/tools
  - 工具既可以是函数工具，也可以是 shell / sandbox / MCP 等能力；在 Agents SDK 里，能力可以直接挂到 agent 上或由外层编排。
- #fetch:https://developers.openai.com/api/docs/guides/reasoning
  - coding 和 multi-step agentic workflows 更适合 reasoning 模型；`reasoning.effort` 是调参旋钮，不是质量兜底手段。
  - 官方建议在函数调用链中保留 reasoning items，尤其是连续多轮工具调用时。
- #fetch:https://developers.openai.com/api/docs/guides/tools-shell
  - shell 既支持 hosted container，也支持 local runtime；官方明确提醒 shell 命令是危险操作，应该 sandbox、限制访问并记录日志。
  - local shell 模式适合对仓库、文件系统和内部工具拥有完整控制权的场景。
- #fetch:https://developers.openai.com/api/docs/guides/agents/sandboxes
  - sandbox 适合需要文件、命令、包、产物、端口和可恢复状态的任务；这与“代码 agent 需要改文件、跑测试、产出 patch”高度一致。
  - 官方将 harness 和 compute 分离，强调控制面放在可信基础设施里，执行面放在隔离 workspace 里。
- #fetch:https://developers.openai.com/api/docs/guides/code-generation
  - OpenAI 把 GPT-5.4 和 Codex 作为 coding agent 的主要推荐入口，并建议 API 侧代码生成优先从 `gpt-5.4` 开始。
- #githubRepo:"openai/openai-cookbook object_oriented_agentic_approach python_code_exec_agent"
  - Cookbook 的 `PythonExecAgent` 示例展示了一个专门的代码执行 agent：它在独立 agent 层里注册 `execute_python_code` 工具，并把代码执行放到隔离容器中。
- #githubRepo:"openai/openai-cookbook tools-evaluation code files"
  - Cookbook 的工具评测示例使用自定义数据集、明确 schema 和 grader 来评估代码文件/符号提取等任务，和本项目现有评测框架的思路一致。

### Project Conventions

- Standards referenced: `frame/core/base_agent.py`、`frame/core/base_llm.py`、`frame/core/llm_orchestrator.py`、`frame/tool/base.py`、`frame/evaluation/harness.py`、`frame/evaluation/metrics.py`、`project-learn` 里的“逐步演化、优先简单、保持可读性”的约束。
- Instructions followed: 仅更新 `./.copilot-tracking/research/` 下的研究文档；未修改任何业务代码、配置或测试文件。

## Key Discoveries

### Project Structure

当前 `CodeAgent` 不是一个真正的专项实现，而是挂在 `BaseAgent` 上的占位类。真正承载行为的是三层结构：`BaseAgent` 管会话和历史，`BaseLLM` / `LLMInvocationOrchestrator` 管多轮工具调用，`frame/tool` 管工具协议和执行。这意味着 code agent 的落地不需要重写框架，只需要在现有扩展口上增加专用工具和专用 turn policy。

### Implementation Patterns

现有 agent 的设计规律非常稳定：差异主要来自工具集合、系统提示词和对一次 turn 的后处理，而不是分叉新的核心架构。`ReactAgent` / `ToolAwareAgent` 已经证明，工具型 agent 可以沿着同一条调用链演进。对 code agent 来说，最重要的是把“代码修改”和“代码验证”都做成明确、可审计、可测试的工具，而不是让模型自己在纯文本里假装完成了任务。

### Complete Examples

```python
# Source: frame/agents/code_agent.py
class CodeAgent(BaseAgent):
    def __init__(self, config, llm, sys_prompt=None, logger=None, session_id=None, memory_hooks=None, agent_id=None):
        super().__init__(config, llm, sys_prompt, logger, session_id, memory_hooks, agent_id)
```

```python
# Source: OpenAI function calling guide
response = client.responses.create(
    model="gpt-5.4",
    tools=tools,
    input=input_list,
)

for tool_call in response.output:
    if tool_call.type != "function_call":
        continue
    args = json.loads(tool_call.arguments)
    result = call_function(tool_call.name, args)
    input_list.append({
        "type": "function_call_output",
        "call_id": tool_call.call_id,
        "output": str(result),
    })
```

### API and Schema Documentation

`frame/tool/base.py` 里的工具协议与 OpenAI function calling 的要求是同构的：工具名、描述、参数 schema、执行结果。结合官方文档，code agent 的工具 schema 应尽量满足 strict mode 约束，特别是：对象参数使用 `additionalProperties: false`，所有字段都显式 required，参数描述要足够具体，便于模型少犯调用错误。

### Configuration Examples

```python
# Source: frame/core/config.py
LLM_MODEL_ID = "llama3"  # 当前默认值来自环境变量
LLM_MAX_ROUNDS = 15
AGENT_MAX_ROUNDS = 15
```

```json
{
  "model": "gpt-5.4",
  "reasoning": { "effort": "high" },
  "tool_choice": "auto"
}
```

### Technical Requirements

- 代码 agent 必须有一个可验证的执行面：至少要能读文件、写 patch、运行测试、查看 diff。
- 代码 agent 的默认运行环境应是 sandbox 或受控 local shell，而不是直接把任意 shell 暴露给模型。
- 工具集应尽量小而明确，优先从“文件查看 / patch 应用 / 测试运行 / 状态检查”四类开始，再决定是否扩展到更宽的 shell 能力。
- 评测必须以客观信号为主，例如测试通过、补丁是否可应用、文件是否按预期变化；主观 rubric 只做辅助。
- 由于当前框架已有评测和记忆骨架，最合理的演进方式是先做单 agent 闭环，再用 eval 逼近更高质量，而不是一开始就上多 agent 协作。

## Recommended Approach

推荐采用“单 agent + sandboxed code tools + evaluator loop”的落地方案。

第一层是把 `CodeAgent` 明确成 `BaseAgent` 的专用子类，但不重做底层编排。它的职责是：接收 coding 任务、生成分步计划、调用受限工具、根据测试反馈继续迭代、最后输出 patch 摘要和验证结果。第二层是新增一组极小而稳定的代码工具，优先覆盖 `read/search`、`apply_patch`、`run_tests`、`git_diff` 四个动作；如果需要进一步的执行能力，再在受控 sandbox 里增加 `shell`，但默认不开放宽权限 shell。第三层是把每次任务都纳入数据集评测，用“补丁能否通过测试、输出是否符合预期、迭代轮数是否可控”来衡量 agent 质量。

这个方案最适合你现在的目标：它足够简单，便于看清 agent 的行为；它足够可测，能把代码质量变成锚点；它也足够有学习价值，因为你可以逐步加工具、加验证、加记忆，而不用一开始就被复杂编排吞掉。

## Implementation Guidance

- **Objectives**: 让 `CodeAgent` 能在单仓库工作区里完成“理解任务 -> 修改代码 -> 跑测试 -> 修正 -> 汇报结果”的完整闭环。
- **Key Tasks**:
  1. 为 `CodeAgent` 设计专用 system prompt，明确只做代码相关任务、输出格式、停止条件和失败回退策略。
  2. 实现最小代码工具集，先覆盖文件读取、搜索、补丁应用、测试执行和 diff 检查。
  3. 把工具执行放进受控 sandbox 或本地受控 shell，确保默认不开放网络和任意命令能力。
  4. 设计 code agent 的离线评测用例，优先用可自动验证的仓库修改任务。
  5. 用现有 `frame/evaluation` 框架建立回归集，按“成功率、测试通过率、修改正确性、迭代轮数”观察优化效果。
  6. 在必要时再补记忆层，用于保留重复犯错、常见修复路径和 repo 特定约束。
- **Dependencies**: `BaseAgent`、`BaseLLM`、`LLMInvocationOrchestrator`、`BaseTool` / `ToolRegistry`、`frame/evaluation`、受控 shell/sandbox 执行层。
- **Success Criteria**: 给定一个小型 coding 任务，agent 能在有限轮次内产出可应用补丁，并通过本地测试或评测脚本验证；评测结果能稳定产出报告，且失败原因能回溯到具体工具或 prompt 问题。