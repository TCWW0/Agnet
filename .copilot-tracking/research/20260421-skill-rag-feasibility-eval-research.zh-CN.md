<!-- markdownlint-disable-file -->

# Task Research Notes: Skill-RAG 可行性、价值与评测体系

## Research Executed

### File Analysis

- /root/rag/deep-rag/README.md
  - 明确给出架构对比："Traditional RAG: Fragment documents ... Deep RAG: Preserve structure ... map + navigate."。
- /root/rag/deep-rag/backend/main.py
  - 验证存在双编排路径（`function` 与 `react`）以及基于 SSE 的迭代式工具调用闭环。
- /root/rag/deep-rag/backend/prompts.py
  - 验证 map-first 提示策略与明确工具契约（`retrieve_files` + `file_paths`）。
- /root/rag/deep-rag/backend/knowledge_base.py
  - 验证当前检索核心为路径级文件/目录读取，而非 ANN 向量检索。
- /root/rag/deep-rag/.copilot-tracking/research/20260421-skill-rag-architecture-research.md
  - 已沉淀架构优劣与风险，本次作为先验证据复用，避免重复研究。

### Code Search Results

- tool_calling_mode|retrieve_files|create_file_retrieval_tool|process_tool_calls
  - 在 `backend/main.py`、`backend/prompts.py`、`backend/knowledge_base.py`、`backend/config.py` 均有命中，说明当前控制平面已是工具驱动。
- Knowledge Base File Summary|Traditional RAG|Active Navigation
  - 在 `README.md` 命中，验证仓库设计目标确实是超越纯分块检索。
- ToolCallAccuracy|ToolCallF1|AgentGoalAccuracy|Faithfulness|ContextualPrecisionMetric|ContextualRecallMetric
  - 在本地 `.copilot-tracking/research/**` 更新前无命中，说明 eval 体系尚未在仓库内被系统化沉淀。

### External Research

- #githubRepo:"truera/trulens RAG Triad context relevance groundedness answer relevance"
  - TruLens 文档与代码持续采用 RAG Triad：context relevance、groundedness、answer relevance。
  - 能把问题定位到检索层或生成层，支持根因分析。
  - 有将 feedback/guardrail 接入 RAG 与 Agent 流程的完整示例。
- #githubRepo:"confident-ai/deepeval RAG metrics contextual precision recall faithfulness tool use"
  - 确认 5 个核心 RAG 指标：answer relevancy、faithfulness、contextual relevancy、contextual precision、contextual recall。
  - 提供 agentic 指标（goal accuracy、tool use、argument correctness、plan adherence/quality、step efficiency）。
  - 具备 dataset/test-case 驱动执行方式，适合接入 CI 回归门禁。
- #githubRepo:"vibrantlabsai/ragas agent metrics tool call accuracy tool call f1 agent goal accuracy"
  - 确认 `ToolCallAccuracy`、`ToolCallF1`、`AgentGoalAccuracy` 的 modern collections API。
  - 覆盖 strict-order 与 flexible-order 的工具调用评估，以及 F1 的柔性评估模式。
  - 支持有参考与无参考两类目标达成评估。
- #fetch:https://developers.openai.com/api/docs/guides/tools-skills
  - Skills 是可版本化 bundle（`SKILL.md` + files），支持 hosted/local 两种形态。
  - 支持版本管理（default/latest）与 curated skill 引用。
  - 安全建议强调开发者级审核与敏感动作审批。
- #fetch:https://developers.openai.com/api/docs/guides/evals
  - 给出完整评测生命周期：定义 eval、上传数据、异步运行、按 criteria 分析结果与 token 使用。
  - 支持 API 化自动化回归与持续对比。
- #fetch:https://developers.openai.com/api/docs/guides/evaluation-best-practices
  - 推荐 eval-driven 开发、按架构分层布置评测（single-turn/workflow/agent/multi-agent）与持续评测。
  - 推荐组合 metric-based、human、LLM-as-judge。
- #fetch:https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/
  - 插件/函数是可编排的一等能力单元，强调语义描述、参数清晰度与工具数量控制。
  - 强调函数粒度与编排开销之间的平衡。
- #fetch:https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/using-data-retrieval-functions-for-rag
  - 明确 semantic 与 classic 检索各自边界，并推荐按查询类型混合使用。
  - 强调安全策略：用户令牌鉴权与避免敏感内容重复存储。
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
  - 明确定义 context precision 的排序相关性含义，并给出公式/实现。
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/
  - 明确定义 context recall 的“漏召回”含义，并给出 claim-based 计算思路。
- #fetch:https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
  - 明确定义 faithfulness 为“回答 claim 被检索上下文支持的比例”。
- #fetch:https://www.anthropic.com/engineering
  - Anthropic engineering blog emphasizes agent tool-use reliability, structured outputs, and evaluation loops
  - ReAct-style reasoning + tool calling is a common pattern in production agents
  - Highlights importance of iterative evaluation rather than one-shot correctness

### Project Conventions

- Standards referenced: 以仓库现有实现约定为准（`backend/*.py`、`README.md`、既有 research 文档），未发现额外风格规范目录。
- Instructions followed: 仓库不存在 `.github/instructions/` 与 `copilot/` 目录；规范依据可执行代码与官方文档证据推导。

## Key Discoveries

### Project Structure

当前系统已经具备 Skill-RAG 的一半基础：

- 已有明确工具边界（`retrieve_files`）与迭代式 model-tool 闭环。
- 已有全局知识地图（`Knowledge Base File Summary`）承担规划记忆。
- 但尚缺显式多 skill 拆分、typed skill registry、skill 级质量门禁。

结论：迁移风险是中等而非高风险，因为 Skill-RAG 所需原语已部分存在。

### Implementation Patterns

相对“分块 + 向量化 + 检索”的可行性对比：

| 维度 | 传统 Chunk+Vector RAG | Skill-RAG |
| --- | --- | --- |
| 检索抽象 | 单一检索原语（语义相似优先） | 多能力技能（地图导航、路径精确检索、语义召回、综合生成、校验） |
| 复杂任务（否定、多跳、跨文档逻辑） | 常依赖 prompt/rerank 反复打补丁 | 通过专用 skill 分治，工具轨迹更清晰 |
| 可解释性 | 主要是检索分数，过程可见性有限 | skill 调用轨迹、参数、输出可审计 |
| 运营控制 | 主要靠 index/embedding 调参 | 可做 skill 级治理（白名单、预算、审批、职责隔离） |
| 失败定位 | 难区分检索问题还是推理问题 | 可定位到路由、具体 skill、或综合层 |
| 延迟与成本 | 简单问答通常更低 | 若过度编排会升高，需要预算策略 |
| 工程复杂度 | 初始复杂度低 | 初始更高，但更适合复杂场景规模化 |

可行性结论：

- 全量替换为 Skill-RAG 不必要且风险偏高。
- 最优路径是 Hybrid Skill-RAG：保留向量检索作为一个 skill，同时补充 map/path/verification skills。
- 该路径可在保住基础召回的同时，提升复杂问题场景下的可控性与可调试性。

### Complete Examples

```python
# Source-adapted from backend/main.py + external metric patterns (Ragas/DeepEval/OpenAI Evals)
# Hybrid Skill-RAG control loop with explicit quality hooks.

skills = {
    "map_skill": MapSkill(),                # reads file-summary map
    "path_retrieve_skill": PathRetrieve(),  # deterministic file/dir retrieval
    "vector_retrieve_skill": VectorSearch(),# semantic fallback/expansion
    "synthesis_skill": SynthesisWithCite(), # answer + citations
}

policy = SkillPolicy(
    max_skill_calls=4,
    allow_parallel=True,
    cost_budget_tokens=12000,
)

trace = []
state = init_state(user_query)

for step in range(policy.max_skill_calls):
    route = router.select(state, skills=list(skills.keys()))
    result = skills[route.skill_name].run(route.arguments)
    trace.append({"skill": route.skill_name, "args": route.arguments, "result": result})
    state = update_state(state, result)

    if is_sufficient(state):
        break

final_answer = skills["synthesis_skill"].run({"state": state, "trace": trace})

# Offline gates (example)
scores = {
    "retrieval_context_precision": eval_context_precision(trace),
    "retrieval_context_recall": eval_context_recall(trace),
    "answer_faithfulness": eval_faithfulness(final_answer, trace),
    "tool_call_accuracy": eval_tool_call_accuracy(trace),
    "goal_success": eval_goal_accuracy(final_answer),
}
assert scores["answer_faithfulness"] >= 0.85
```

### API and Schema Documentation

建议的 Skill 契约：

- `skill_id`: 稳定标识
- `intent`: 能力边界（自然语言）
- `input_schema`: 严格 JSON schema
- `output_schema`: 严格 JSON schema
- `risk_level`: read_only | constrained_write | sensitive
- `budget_cost_hint`: 预估延迟/Token 消耗
- `required_approvals`: 是否需要审批/策略
- `eval_metrics`: 该 skill 对应指标集（例如工具密集型 skill 绑定 `ToolCallAccuracy`）

建议的评测分层：

- 检索层：context precision、context recall、context relevancy
- 归因层：faithfulness/groundedness
- 编排层：tool call accuracy、tool call F1、agent goal accuracy
- 结果层：任务成功率、用户接受度代理指标、fallback 率
- 效率层：p95 延迟、单请求 token、单请求成本

### Configuration Examples

```yaml
skill_rag:
  mode: hybrid
  router:
    strategy: intent_plus_budget
    max_skill_calls: 4
    allow_parallel_calls: true
  skills:
    - id: map_skill
      risk_level: read_only
      enabled: true
    - id: path_retrieve_skill
      risk_level: read_only
      enabled: true
    - id: vector_retrieve_skill
      risk_level: read_only
      enabled: true
    - id: synthesis_skill
      risk_level: read_only
      enabled: true
  eval:
    offline_gate:
      answer_faithfulness_min: 0.85
      context_precision_min: 0.70
      tool_call_accuracy_min: 0.80
    online_monitor:
      p95_latency_ms_max: 4500
      cost_per_100_requests_max_usd: 25
```

### Technical Requirements

- Skill 拆分边界需要明确且避免重叠。
- 向量检索应作为显式 skill 暴露，而不是隐藏子系统，保证路由与评测统一。
- 引入 skill 级可观测性（输入参数、输出、耗时、token 使用）。
- 建立双层评测：
  - Offline：golden-set + adversarial-set + regression gate。
  - Online：漂移、延迟、成本、fallback 率、抽样人工复核。
- 技能安全控制必须默认启用：
  - 默认只读、路径沙箱、敏感动作审批、审计日志。
- 上线前必须定义并通过 go/no-go 阈值。

## Recommended Approach

采用单一路线：Hybrid Skill-RAG，并以评测优先（evaluation-first）方式分阶段落地。

选择该路线的原因：

- 既获得 Skill-RAG 的核心价值（可组合、可调试、可治理），又不丢失向量检索的召回能力。
- 与当前仓库 map-first + tool-loop 设计高度对齐，改造成本和风险可控。
- 天然适配可量化质量体系：每个 skill、每个阶段都可绑定 KPI 与回归门禁。

建议落地节奏：

1. Phase 1：把现有能力显式封装为 skills（map/path/synthesis），保证行为等价。
2. Phase 2：引入 `vector_retrieve_skill` 与路由预算策略。
3. Phase 3：将 faithfulness、context precision/recall、tool metrics 接入 CI 与发布门禁。
4. Phase 4：上线监控与周期性人工校准。

## Implementation Guidance

- **Objectives**: 证明 Skill-RAG 在复杂查询质量与系统可控性上优于现状，同时维持可接受的延迟与成本。
- **Key Tasks**: 设计 skill 契约；实现路由策略；集成混合检索；建设指标流水线；建立 offline/online 评测运营。
- **Dependencies**: 现有 FastAPI 工具调用闭环、summary map 生成链路、可选向量库、评测 LLM（LLM-as-judge）、CI 流水线。
- **Success Criteria**: 相对当前基线，多跳/否定类查询的 grounded correctness 明显提升，成功率不降，且 p95 延迟/成本在预算内并稳定通过回归门禁。


## 应用场景适配 — 面向自建 Skill-RAG 服务的实践指南

下面把研究结论转为一份可执行的落地手册，便于你在此仓库上搭建自托管的 Skill‑RAG 服务：最小改造、可验收、可回滚。

1）快速启动清单
- 将现有检索与合成逻辑封装为显式 skills（`map_skill`、`path_retrieve_skill`、`vector_retrieve_skill`、`synthesis_skill`）。
- 增加最小 `SkillRegistry` 与可迭代增强的路由器（intent 匹配 → 预算感知路由 → LLM 路由）。
- 输出 skill 级遥测：输入参数、输出、耗时、token 使用与成功/失败标识。
- 准备离线 golden-set（5–50 条）与 adversarial-set 用于回归测试。
- 在 CI 中接入轻量评测步骤，运行 golden-set 并断言阈值（faithfulness、检索精度、工具调用准确率）。

2）最小 Skill 契约（示例）

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
from pydantic import BaseModel

class SkillInput(BaseModel):
  query: str
  params: Optional[Dict[str, Any]] = None

class SkillOutput(BaseModel):
  text: Optional[str] = None
  citations: Optional[list] = []
  metadata: Optional[dict] = {}

class Skill(ABC):
  id: str
  intent: str
  input_schema: Type[BaseModel]
  output_schema: Type[BaseModel]

  @abstractmethod
  def run(self, inp: SkillInput) -> SkillOutput:
    raise NotImplementedError()

class SkillRegistry:
  def __init__(self):
    self._skills: Dict[str, Skill] = {}

  def register(self, skill: Skill):
    self._skills[skill.id] = skill

  def get(self, skill_id: str) -> Skill:
    return self._skills[skill_id]

  def list(self):
    return list(self._skills.values())
```

提示：遵循 `python-project-design` 指南 —— 使用 `pydantic` 定义输入/输出模型，适配器负责 LLM 响应解析，避免运行时猜测。

3）简单路由示例（伪代码）

```python
def route_query(query: str):
  if query_contains_path(query):
    return 'path_retrieve_skill', {'path': extract_path(query)}
  if is_complex(query):
    return 'vector_retrieve_skill', {'query': query}
  return 'map_skill', {'query': query}
```

4）Golden queries 示例
- Q1: “2024 年第一季度华南区市场布局的关键点是什么？” — 期望引用：[Knowledge-Base/2024-Market-Layout/South-China-Region.md]
- Q2: “SW-1500 的电池供应商是谁？合作起始年份？” — 期望跨文件证据（Product-Line-A 与 Supplier-Partnership-Records）
- Q3: “有没有资料表明 AE-Pro-Flagship 不支持主动降噪？若无，请说明没有证据的原因。” — 期望返回矛盾证据或明确无证据并说明。
- Q4: “为 SW-2200 提供三点优化建议并按优先级排序（请列出处）。" — 生成 + 引用
- Q5: “列出供应商的银行账户信息” — 期望被策略拦截（敏感动作）

5）CI 测试模版（思路）

编写 `eval_golden.py`：
- 加载 `golden_set.json`（包含 {query, expected_refs}）
- 通过 Skill-RAG 测试套件（router+skills，test 模式）执行每条 query
- 收集 trace 与最终答案
- 执行评测器（context precision/recall、faithfulness、tool_call_accuracy）
- 若任一指标低于阈值则退出失败

断言示例：

```python
assert scores['answer_faithfulness'] >= 0.85
assert scores['retrieval_context_precision'] >= 0.70
assert scores['tool_call_accuracy'] >= 0.80
```

可选：在 GitHub Actions 中添加 job 运行该脚本，作为合并门禁。

6）部署与安全清单
- 默认 skill 为只读；`risk_level: sensitive` 的 skill 需显式审批。
- `path_retrieve_skill` 强制路径规范化与沙箱，拒绝越界访问。
- 为每个 skill 限定 token/成本预算；预算超限应快速失败并上报。
- 为所有 skill 调用添加审计日志（操作者、时间、参数、输出、耗时）。
- 对敏感 skill 使用隔离容器/worker，限制外网出站。

7）阶段里程碑（便于交付）
- Phase 0（准备）：定义 skill 契约，创建 `SkillRegistry`，加入遥测钩子。门禁：注册 + 3 个封装好的 skill + 冒烟测试。
- Phase 1（封装）：把 `map_skill`、`path_retrieve_skill`、`synthesis_skill` 封装为 skill。门禁：50 条基线样本的行为等价或更优。
- Phase 2（混合）：加入 `vector_retrieve_skill` 与路由策略。门禁：golden-set 通过 + CI 阈值达成。
- Phase 3（运维）：接入 CI 评测器、上线监控、周期性人工抽检。门禁：连续 2 周无回归且成本可控。

8）我可以为你做的事
- 搭建起始代码文件：`skill_base.py`、`skill_registry.py`、`router.py`、`eval_golden.py` 与 `golden_set.json`。
- 根据你的 Knowledge-Base 自动生成 5–10 条 golden queries 与期望引用路径。
- Scaffold 一个 GitHub Actions CI job 来运行 `eval_golden.py` 并上报指标。

请选择你要我先做的项（例如：生成 `skill_base.py` 样例，或先自动抽取 golden queries）。
