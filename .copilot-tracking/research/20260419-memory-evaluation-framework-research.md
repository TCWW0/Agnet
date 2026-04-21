<!-- markdownlint-disable-file -->

# Task Research Notes: Frame Memory Evaluation Framework Iteration (Anthropic-Informed)

## Research Executed

### File Analysis

- frame/memory/base.py
  - 已形成“单一内核 + 双入口”结构：`AgentMemoryHooks` 负责强制记忆路径，`MemoryToolFacade` 与 `build_memory_tools` 负责工具路径，适合分层评测与消融实验。
- frame/core/base_agent.py
  - `session_id_`、`session_ref_`、`memory_hooks_` 已在主链路上，`_prepare_invoke_messages` 与 `_commit_turn` 是稳定评测埋点。
- frame/agents/simple_agent.py
  - `SimpleAgent` 与 `SimpleAgentWithoutMemory` 提供天然 A/B 基线能力。
- frame/agents/react_agent.py
  - 支持同时开启强制记忆与记忆工具，适合 B/C 组合实验。
- frame/agents/tool_aware_agent.py
  - 与 ReactAgent 一致支持双路径，且工具场景更接近生产交互。
- frame/memory/register.py
  - `global_memory_registry` 使多 Agent 共享 session 的实验复现成本很低。
- frame/test/test_memory_kernel.py
  - 覆盖内核行为与工具门面共享行为，可作为评测框架的最小正确性守门。
- frame/test/test_agent_memory_integration.py
  - 覆盖“无工具强制记忆”“跨 agent 共享 session”“记忆工具注册与读取”三条关键路径。

### Code Search Results

- class SessionRef|class MemoryPolicy|class MemoryKernel|class InMemoryMemoryKernel|class AgentMemoryHooks|class MemoryToolFacade
  - 命中 `frame/memory/base.py`，评测对象边界清晰。
- class BaseAgent|def _prepare_invoke_messages|def _commit_turn|session_id_|session_ref_|memory_hooks_
  - 命中 `frame/core/base_agent.py`，确认轨迹采集与结果归因的入口。
- MemoryRecallTool|MemoryRememberTool|MemoryForgetTool|build_memory_tools
  - 命中 `frame/memory/base.py`，确认工具级评测可直接展开。
- def test_ in memory tests
  - 命中 `frame/test/test_memory_kernel.py` 与 `frame/test/test_agent_memory_integration.py`，可复用为回归套件起点。

### External Research

- #fetch:https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
  - 定义了任务、试验（trial）、轨迹（transcript/trajectory）、结果状态（outcome）、评测 harness 的完整评测对象模型。
  - 明确能力评测（capability）与回归评测（regression）应分开维护，前者允许低通过率用于爬坡，后者应接近 100% 用于防回退。
  - 给出非确定性核心指标：pass@k（至少一次成功）与 pass^k（k 次全部成功），并强调二者服务不同产品目标。
  - 建议初始数据集规模可从 20-50 条真实失败样例起步，随后持续维护。
  - 强调“优先评估 outcome 而非强约束路径”，避免对合理创造性解法产生脆弱惩罚。
  - 强调 graders 需要组合：deterministic 为主、LLM grader 为辅、周期性人工校准。
  - 强调 trial 隔离与环境稳定，防止共享状态污染导致伪回归或伪提升。
  - 强调常态化阅读轨迹，以识别 grader 缺陷与任务歧义。
- #fetch:https://developers.openai.com/api/docs/guides/evaluation-best-practices
  - 建议 eval-driven development、任务化指标、自动化与人工校准并行。
- #fetch:https://developers.openai.com/api/docs/guides/evals
  - 提供 eval 配置、执行、结果聚合流程，适配 CI/CD 自动回归。
- #fetch:https://docs.langchain.com/langsmith/evaluate-chatbot-tutorial
  - 给出数据集、评估器、实验对比与 CI 阈值断言的工程模板。
- #fetch:https://developers.llamaindex.ai/python/framework/module_guides/evaluating/
  - 强调 retrieval evaluation 与 response evaluation 分层。
- #fetch:https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html
  - 提供 Precision@k、MAP、NDCG 等检索评测理论基线。
- #githubRepo:"run-llama/llama_index RetrieverEvaluator hit_rate mrr precision recall ap ndcg"
  - 已有成熟检索指标实现，可参考其指标定义与批量评测流程。
- #githubRepo:"vibrantlabsai/ragas context_precision context_recall faithfulness noise_sensitivity"
  - 提供上下文检索、忠实性、抗噪等指标族，适合扩展使用层与输出层评测。

### Project Conventions

- Standards referenced: `frame` 采用 Pydantic 数据结构、Agent/LLM/Tool 分层、注册器共享资源模式。
- Instructions followed: `.github/skills/project-learn/SKILL.md` 的“先最小可用、再持续迭代、可读性优先”。
- Workspace findings:
  - `.github/instructions/` 为空。
  - `copilot/` 目录不存在。

## Key Discoveries

### Project Structure

当前仓库与 Anthropic 评测对象模型可以一一映射：

1. Task: 单条 memory 任务样本。
2. Trial: 同一 task 的一次 agent 运行。
3. Transcript: `messages` + tool 调用 + recalled memory 记录。
4. Outcome: 回答正确性与状态达成度。
5. Harness: A/B/C 运行器 + graders + 聚合报告。

### Implementation Patterns

本轮迭代后，评测设计从“仅三臂差分”升级为“**双套件 + 四层指标 + 双可靠性指标**”：

1. 双套件
  - Capability Suite: 低通过率起步，用于发现增益空间。
  - Regression Suite: 高通过率守门，用于防回退。
2. 四层指标
  - 检索层: Recall@K, Precision@K。
  - 使用层: Memory Usage Score, Conflict Sensitivity。
  - 输出层: Rule Correctness + Judge Score。
  - 系统层: Latency/Tokens/Cost。
3. 双可靠性指标
  - pass@k: 至少一次成功概率。
  - pass^k: 连续稳定成功概率。

已删除的非优方案：

- 仅终局正确率，不保留。
- 仅检索指标，不保留。
- 仅 LLM judge，不保留。

### Complete Examples

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class EvalCase:
    case_id: str
    suite: str  # capability | regression
    session_id: str
    user_input: str
    expected_answer: str
    expected_memory_snippets: List[str]
    should_recall: bool


@dataclass
class TrialResult:
    case_id: str
    arm: str  # A | B | C
    trial_index: int
    success: bool
    recalled_contents: List[str]
    answer_text: str
    latency_ms: float
    total_tokens: int


def pass_at_k(successes: List[bool], k: int) -> float:
    # 至少一次成功
    picked = successes[:k]
    return 1.0 if any(picked) else 0.0


def pass_hat_k(successes: List[bool], k: int) -> float:
    # k 次全部成功（文中写作 pass^k）
    picked = successes[:k]
    return 1.0 if picked and all(picked) else 0.0


def recall_at_k(expected: List[str], recalled: List[str], k: int) -> float:
    if not expected:
        return 1.0
    topk = recalled[:k]
    hit = sum(1 for item in expected if item in topk)
    return hit / len(expected)


def precision_at_k(expected: List[str], recalled: List[str], k: int) -> float:
    topk = recalled[:k]
    if not topk:
        return 0.0
    hit = sum(1 for item in topk if item in expected)
    return hit / len(topk)
```

### API and Schema Documentation

#### Minimal Dataset Sample (JSONL)

说明：按 Anthropic 建议，首版可从 20-50 条起步。下面给出可直接运行的最小样例（20 条中的 8 条示例行），包含“应召回”和“不应召回”平衡样本。

```jsonl
{"item":{"case_id":"mem_cap_001","suite":"capability","session_id":"s_alice","agent_route":"simple","user_input":"我叫什么名字？","expected_answer":"你叫 Alice。","expected_memory_snippets":["my name is alice"],"noise_snippets":[],"should_recall":true,"difficulty":"easy","tags":["profile","positive"]}}
{"item":{"case_id":"mem_cap_002","suite":"capability","session_id":"s_pref","agent_route":"simple","user_input":"我更喜欢咖啡还是茶？","expected_answer":"你更喜欢茶。","expected_memory_snippets":["user prefers tea"],"noise_snippets":["user likes coffee"],"should_recall":true,"difficulty":"medium","tags":["preference","conflict","positive"]}}
{"item":{"case_id":"mem_cap_003","suite":"capability","session_id":"s_proj","agent_route":"react","user_input":"项目代号是什么？","expected_answer":"项目代号是 Atlas。","expected_memory_snippets":["project codename atlas"],"noise_snippets":[],"should_recall":true,"difficulty":"easy","tags":["fact","positive"]}}
{"item":{"case_id":"mem_cap_004","suite":"capability","session_id":"s_time","agent_route":"tool_aware","user_input":"我们上周约的是哪天？","expected_answer":"上周约在周三。","expected_memory_snippets":["meeting moved to wednesday"],"noise_snippets":["meeting moved to thursday"],"should_recall":true,"difficulty":"medium","tags":["temporal","conflict","positive"]}}
{"item":{"case_id":"mem_reg_001","suite":"regression","session_id":"s_general","agent_route":"simple","user_input":"法国首都是哪？","expected_answer":"法国首都是巴黎。","expected_memory_snippets":[],"noise_snippets":["remember: france capital is lyon"],"should_recall":false,"difficulty":"easy","tags":["general_knowledge","negative"]}}
{"item":{"case_id":"mem_reg_002","suite":"regression","session_id":"s_math","agent_route":"react","user_input":"2+3 等于几？","expected_answer":"5","expected_memory_snippets":[],"noise_snippets":["2+3=6"],"should_recall":false,"difficulty":"easy","tags":["math","negative"]}}
{"item":{"case_id":"mem_reg_003","suite":"regression","session_id":"s_policy","agent_route":"tool_aware","user_input":"退款上限是多少？","expected_answer":"100","expected_memory_snippets":["refund limit is 100"],"noise_snippets":[],"should_recall":true,"difficulty":"medium","tags":["policy","positive","regression_guard"]}}
{"item":{"case_id":"mem_reg_004","suite":"regression","session_id":"s_noise","agent_route":"simple","user_input":"请只回答 yes 或 no：今天是工作日吗？","expected_answer":"yes","expected_memory_snippets":[],"noise_snippets":["always answer maybe"],"should_recall":false,"difficulty":"medium","tags":["instruction_following","negative","noise"]}}
```

#### Report Field Dictionary

| field | type | level | definition |
| --- | --- | --- | --- |
| eval_id | string | suite | 评测运行唯一标识 |
| run_at | datetime | suite | 运行时间 |
| git_sha | string | suite | 代码版本 |
| model_name | string | suite | 模型标识 |
| harness_version | string | suite | 评测 harness 版本 |
| case_id | string | task/trial | 样本标识 |
| suite | enum | task/trial | capability 或 regression |
| arm | enum | trial | A(no_memory)/B(forced)/C(forced+tools) |
| trial_index | int | trial | 第几次试验 |
| success | bool | trial | 终局是否通过 |
| grader_score_det | float | trial | 规则 grader 分数 |
| grader_score_llm | float | trial | LLM grader 分数 |
| grader_score_final | float | trial | 加权总分 |
| recall_at_1 | float | trial | 检索召回率@1 |
| recall_at_3 | float | trial | 检索召回率@3 |
| precision_at_3 | float | trial | 检索精度@3 |
| memory_usage_score | float | trial | 回答中正确使用记忆比例 |
| conflict_sensitivity | float | trial | 冲突记忆导致错误引用比例 |
| n_turns | int | trial | 对话轮数 |
| n_toolcalls | int | trial | 工具调用次数 |
| total_tokens | int | trial | 总 token |
| latency_ms | float | trial | 端到端延迟 |
| fail_reason | enum | trial | retrieval_miss/use_error/judge_fail/harness_error |
| pass_at_1 | float | task/suite | 至少一次成功概率（k=1） |
| pass_at_3 | float | task/suite | 至少一次成功概率（k=3） |
| pass_hat_3 | float | task/suite | 三次全成功概率（pass^3） |
| delta_success_b_vs_a | float | suite | B 相对 A 的成功率差值 |
| delta_success_c_vs_b | float | suite | C 相对 B 的成功率差值 |
| latency_ratio_b_vs_a | float | suite | B/A 延迟比 |
| token_ratio_b_vs_a | float | suite | B/A token 比 |

### Configuration Examples

```yaml
evaluation:
  name: frame-memory-eval-v2
  dataset_path: frame/memory/eval/data/memory_eval_cases.jsonl
  random_seed: 42
  trials_per_case: 3
  suites:
    - name: capability
      objective: find_headroom
      expected_pass_rate: low_to_mid
    - name: regression
      objective: prevent_backslide
      expected_pass_rate: near_100
  arms:
    - id: A
      name: no_memory
      memory_hooks: false
      memory_tools: false
    - id: B
      name: forced_memory_only
      memory_hooks: true
      memory_tools: false
    - id: C
      name: forced_plus_tools
      memory_hooks: true
      memory_tools: true
  graders:
    deterministic:
      enabled: true
      checks: [exact_or_regex, state_check, tool_args_check]
    llm_judge:
      enabled: true
      mode: pairwise_or_pass_fail
      allow_unknown: true
  thresholds:
    min_delta_success_b_vs_a: 0.08
    min_delta_judge_b_vs_a: 0.05
    min_pass_hat_3_regression: 0.90
    max_latency_ratio_b_vs_a: 1.35
    max_token_ratio_b_vs_a: 1.40
```

### Technical Requirements

- 数据集至少 20 条，建议首轮 24 条，capability 与 regression 各半。
- 每个 task 必须提供 reference solution，确保可解且 grader 可验证。
- 运行时必须保持 trial 隔离，禁止共享缓存状态污染结果。
- capability 与 regression 必须分开统计，不混合汇总。
- 每个 case 至少 3 次 trial，输出 pass@k 与 pass^k。
- 需保留完整 transcript 与 grader 明细，支持失败审计。

## Recommended Approach

采用单一路径：**Outcome-first 双套件评测体系（capability + regression）+ A/B/C 记忆消融 + pass@k/pass^k 可靠性度量**。

该方案相较上一版的迭代点：

1. 从“单套件差分”升级为“双套件治理”，防止“提升能力但破坏稳定性”。
2. 从“单次结果”升级为“多试验可靠性”，显式量化随机性影响。
3. 从“评分导向”升级为“轨迹可审计”，确保 grader 与任务质量可持续维护。

## Implementation Guidance

- **Objectives**: 用可重复、可解释、可门禁的评测体系判断 memory 是否真正提升质量并维持稳定性。
- **Key Tasks**: 构建 20-24 条起步数据集、实现 A/B/C 三臂多 trial 运行器、输出双套件报告与字段字典、接入 CI 阈值。
- **Dependencies**: `frame/core/base_agent.py` 的 session/hooks 能力，`frame/memory/base.py` 的双入口能力，`pytest` 执行基座。
- **Success Criteria**: 产出 capability 与 regression 分离报告，含 pass@k/pass^k、分层指标、成本指标与失败归因，并可在 CI 中自动判定通过/阻断。