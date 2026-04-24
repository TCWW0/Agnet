<!-- markdownlint-disable-file -->

# Task Research Notes: Code Agent 设计演进与下一步架构研究

## Research Executed

### File Analysis

- frame/agents/code_agent.py
  - `CodeAgent` 已经演进为显式的专项控制器，不再只是转发构造参数；它现在包含语义化阶段枚举、阶段级工具选择、手动工具执行、todo 持久化、任务状态背压提醒和进度日志埋点。
- frame/agents/simple_agent.py
  - 这是最轻量的 `BaseAgent` 使用范式，说明当前框架允许“只定 prompt + LLM 调用 + commit turn”的最小 agent。
- frame/agents/react_agent.py
  - 已经存在工具注册、流式输出和自动工具执行的完整实现，是最接近“可扩展专项 agent”的参考样板。
- frame/agents/tool_aware_agent.py
  - 与 `ReactAgent` 一样复用了 `BaseAgent -> BaseLLM -> ToolRegistry` 结构，证明“新 agent 主要靠工具集合和提示词分化”是当前主路径。
- frame/agents/tmp.py
  - 这是过渡期的手动工具执行原型，已经证明“模型先产出工具调用、再由 agent 本层执行工具、再把工具结果喂回模型”比完全交给 orchestrator 更容易做控制和调试。
- frame/core/base_agent.py
  - 负责会话、历史消息、记忆钩子和 turn commit，是所有 agent 的通用控制面。
- frame/core/base_llm.py
  - 已经封装了流式与非流式调用、工具模式选择、最大轮次和回调，是代码 agent 复用的核心调用层。
- frame/core/llm_orchestrator.py
  - 现成的多轮 tool call 状态机已经具备“模型调用工具 -> 执行 -> 回传 -> 再调用”的闭环；但当 `tool_mode=AUTO` 时，执行权仍然在编排层，不在 code agent 本层。
- frame/tool/base.py
  - `BaseTool` / `ToolDesc` / `ToolResponse` 已经定义了工具 schema、参数校验和输出结构，是代码操作工具的自然扩展点。
- frame/tool/register.py
  - 工具注册器很薄，当前没有 namespace 或隔离能力，意味着代码 agent 要靠更细的工具设计来控制暴露面。
- frame/tool/builtin/run_command.py
  - `run_command` 已经被收敛成严格结构化输入：只保留 `command + args + timeout_sec`，并用 `enum` 约束 `command`，这能显著减少模型输出裸命令或重复无效命令的概率。
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
  - 当前只命中 `frame/agents/code_agent.py`，说明专项行为集中在这一处控制面，没有分叉实现干扰。
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

当前 `CodeAgent` 已经成为专项控制器，但底层仍然沿用现有三层结构：`BaseAgent` 管会话和历史，`BaseLLM` / `LLMInvocationOrchestrator` 提供 LLM 调用能力，`frame/tool` 提供工具协议和执行。现在的关键变化是，工具执行权已经从“自动编排层”收回到 `CodeAgent`，而不是仍然全部交给 orchestrator。

### Implementation Patterns

现有 agent 的设计规律非常稳定：差异主要来自工具集合、系统提示词和对一次 turn 的后处理，而不是分叉新的核心架构。`ReactAgent` / `ToolAwareAgent` 已经证明，工具型 agent 可以沿着同一条调用链演进。对 code agent 来说，最重要的是把“代码修改”“代码验证”“状态更新”做成明确、可审计、可测试的工具和状态，而不是让模型在纯文本里自说自话。

当前实现之所以能工作，核心原因有四个：

1. 阶段被显式拆开，analysis / generation / verification 不再混在一个长 prompt 里。
2. 工具执行权收回到 agent 本层，LLM 只负责产出工具调用与文本，不负责自己替模型执行。
3. todo 成为可持久化的任务状态载体，agent 能判断“模型是否长期没有更新任务状态”。
4. `run_command` 被格式化为强约束输入，避免模型继续发出裸 `python` 这种低信息、重复率高的调用。

对照来看，先前实现之所以难以稳定达到现在的效果，主要是因为它把自动工具执行交给了 orchestrator，phase 工具集合过宽，且缺少任务状态背压：

1. `tool_mode=AUTO` 时，工具执行会被编排层自动循环，agent 本层无法决定什么时候执行、什么时候暂停、什么时候插入提醒。
2. 早期阶段只是在 prompt 中描述“应该做什么”，但没有把“当前任务做到哪一步”变成可读写状态。
3. `run_command` 的输入协议过松时，模型容易反复输出 `python` 这种无效命令，而不是完整的可执行命令行。
4. 没有结构化的阶段语义和 backpressure 计数，导致一旦模型偏航，agent 很难把注意力拉回当前任务。

### Complete Examples

```python
# Source: frame/agents/code_agent.py
class CodeAgentPhase(str, Enum):
  ANALYSIS = "analysis"
  GENERATION = "generation"
  VERIFICATION = "verification"
```

```python
# Source: frame/tool/builtin/run_command.py
params = ToolParameters(
  properties={
    "command": Property(type="string", enum=["python", "python3", "pytest", "g++", "make", "git"]),
    "args": Property(type="string"),
    "timeout_sec": Property(type="integer"),
  },
  required=["command"],
)
```

### API and Schema Documentation

`frame/tool/base.py` 里的工具协议与 OpenAI function calling 的要求是同构的：工具名、描述、参数 schema、执行结果。结合官方文档，code agent 的工具 schema 应尽量满足 strict mode 约束，尤其要避免宽松的“自然语言拼命令”输入。当前 `run_command` 的演进方向是从“一个字符串”变成“命令标识 + 参数字符串 + 明确允许集”，这样更容易限制滥用，也更容易让模型学会稳定调用。

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

- 代码 agent 必须有一个可验证的执行面：读文件、写 patch、跑测试、看 diff 都应是明确动作。
- 代码 agent 的默认运行环境应是 sandbox 或受控 local shell，而不是直接把任意 shell 暴露给模型。
- 工具集应尽量小而明确，优先从“文件查看 / patch 应用 / 测试运行 / 状态检查”四类开始，再决定是否扩展到更宽的 shell 能力。
- 任务状态必须是可持久化、可查询、可重置的，否则背压只会停留在 prompt 里。
- 评测必须以客观信号为主，例如测试通过、补丁是否可应用、文件是否按预期变化；主观 rubric 只做辅助。
- 由于当前框架已有评测和记忆骨架，最合理的演进方式是先做单 agent 闭环，再用 eval 逼近更高质量，而不是一开始就上多 agent 协作。

## Recommended Approach

推荐采用“单 agent 控制面 + 强约束工具层 + 结构化可观测性 + evaluator loop”的架构。

第一层是把 `CodeAgent` 继续做成显式控制器：保留阶段枚举、phase policy、todo 状态、backpressure 计数和失败分类，但把这些逻辑拆成更小的内部模块，而不是继续堆在一个大类里。第二层是把工具层保持小而强约束：`read/search/list_dir` 负责观察，`apply_patch/write_file` 负责修改，`run_tests` 负责验证，`run_command` 只作为受限逃生口；如果某类命令频繁出现，优先拆成专用工具，而不是继续扩大 `run_command` 的职责。第三层是把一次执行的全过程结构化输出：每个阶段、每次工具调用、每次状态变化都写成可视化 trace，便于 debug、回放和评估。

如果按优先级排序，下一步最值得做的不是“再加更多聪明 prompt”，而是：

1. 把 phase / tool / task state 抽成更清晰的结构体或枚举。
2. 把 tool event、todo 变化、backpressure 触发写成结构化日志或 JSONL trace。
3. 给 `run_command` 再加一层命令族分流，重复高频命令优先拆成独立工具。
4. 用评测数据集把“是否遵守指令”“是否减少无效调用”“是否更少重复工具请求”量化出来。

## Implementation Guidance

- **Objectives**: 让 `CodeAgent` 在保持简单的前提下，继续提升“少走偏路、少重复调用、少依赖大 prompt”的能力。
- **Key Tasks**:
  1. 把当前阶段控制、任务状态监控和工具执行分成独立的内部协作单元。
  2. 给每类高频工具建立结构化 schema 和统一失败分类。
  3. 输出执行 trace，支持阶段级、工具级和任务级可视化回放。
  4. 用评测数据集持续衡量“无效调用次数”“状态回收次数”“完成轮次”和“测试通过率”。
- **Dependencies**: `BaseAgent`、`BaseLLM`、`LLMInvocationOrchestrator`、`BaseTool` / `ToolRegistry`、`frame/evaluation`、受控 shell/sandbox 执行层。
- **Success Criteria**: 给定一个小型 coding 任务，agent 能在有限轮次内产出可应用补丁，并通过本地测试或评测脚本验证；同时能在 trace 里看见任务状态变化、背压触发点和工具失败原因。