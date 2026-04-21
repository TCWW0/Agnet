# 评判体系设计与系统使用文档

日期：2026-04-20

概述
- 目标：定义一套可复现、可聚合的评测体系，用以衡量 memory 子系统（如 InMemoryMemoryKernel）在不同场景下的效果、健壮性与成本。
- 适用范围：面向 frame/evaluation 内现有的 harness/grader/metrics 实现（EvalCase、EvalConfig、EvalExecutor、grader、report 聚合链路）。

设计目标
- 正确性优先（outcome-first）：评判首先以输出正确性为主，避免将实现细节（是否使用 memory）作为硬性门槛。
- 可比性：通过 arm（A/B/C）对照实验，量化 memory 开启/关闭、hooks vs tools 带来的增益与成本。
- 鲁棒性：对噪声（noise snippets）、冲突（conflicting facts）与部分匹配场景进行刻画。
- 成本意识：同时度量 token/latency 开销，便于做收益—成本权衡。

核心概念映射
- Dataset / EvalCase：逐行 JSONL。单条 case 包含 session_id、user_input、expected_answer、expected_memory_snippets、noise_snippets、should_recall 等字段。
- Arms：预定义的实验臂集合（默认 A/B/C）
  - A：基线（不使用 memory）
  - B：使用 memory hooks（runtime 内联检索）
  - C：使用 memory 工具（显式工具调用检索）
- Trials：每个 case 可重复运行多次（随机化或多次抽样），聚合出 pass@k 类型指标。
- EvalExecutor：执行器协议（frame/evaluation/harness.py 中定义），负责把 case 转换为被评测系统的调用并收集观测（TrialObservation/TrialScore/TrialResult）。
- Grader：对单次 trial 的输出给分（frame/evaluation/grader.py），包含正确性判定、冲突敏感性、记忆使用评分等。
- 报表：从 trial -> case -> arm -> suite 聚合并计算 delta（B vs A、C vs B）。

主要指标（简要说明）
- pass@k：在同一 case 下多次 trial，如果有至少一条 trial 成功，则视为通过。用于衡量在多次尝试/随机化下的成功概率。
- pass_hat_k：对 pass@k 的无偏估计（针对小样本场景）。
- recall@k / precision@k：针对 memory 检索返回的 snippets 与期望片段之间的召回与精确度（若执行器暴露检索排名/候选）。
- conflict_sensitivity：当检索到与期望不一致（噪声/冲突）时，模型输出错误的概率或惩罚系数。
- mean_total_tokens / mean_latency_ms：用于估算 token 成本与响应延迟。

成功判定（Grader 行为要点）
- Outcome-first：若输出与 expected_answer 匹配（按规范化/归一化规则），优先判定为成功。
- 冲突/噪声检测：若检索到冲突片段并导致错误回答，计入 conflict_sensitivity 指标；grader 可将冲突作为软惩罚而非直接否决。
- 记忆使用评分：作为解释性指标（是否使用 memory、使用量），不作为硬性通过门槛（已在实现中放宽）。

聚合方法
- Case -> Arm 汇总：对相同 case 与 arm 的多个 trial 汇总为通过率、pass@k、平均 token/延迟等。
- Arm Suite Summary：把同一 suite（capability/regression 等）下的所有 case 在同一 arm 上做聚合。
- Suite Delta：计算 arm 之间的差值（例如 B vs A），用于量化记忆引入的净效益与成本。

实现位置（代码映射）
- 数据加载：frame/evaluation/dataset.py
- 域模型：frame/evaluation/models.py
- 指标实现：frame/evaluation/metrics.py
- Grader：frame/evaluation/grader.py
- Harness / Executor Protocol：frame/evaluation/harness.py
- 报表聚合：frame/evaluation/report.py
- memory 专用执行器示例：frame/evaluation/memory/executor.py
- memory runner（示例）：frame/evaluation/memory/run_memory_eval.py

使用说明（快速上手）
1. 在虚拟环境中运行示例 runner（项目根目录）：

```bash
/root/agent/.venv/bin/python frame/evaluation/memory/run_memory_eval.py
```

2. 输出目录（示例脚本生成）：
- frame/evaluation/memory/outputs/report.json —— 完整的 EvalReport（JSON 可序列化字典）。
- frame/evaluation/memory/outputs/summary.txt —— 人类可读的摘要。

3. 报告关键字段（EvalReport 常见字段）：
- eval_id, run_at, config
- arm_suite_summaries: 每个 arm 的聚合统计（case_count, trial_count, success_rate, pass_at_1, pass_at_k, mean_total_tokens, mean_latency_ms）
- suite_deltas: B vs A、C vs B 的 delta 指标（成功率差、延迟/token 比率等）

示例解读：
- 关注成功率增益与 token/latency 增加的 trade-off。若成功率提升明显且 token/latency 削弱可接受，则 memory 引入值得采纳。

设计注意事项与扩展方向
- 增强匹配策略：当前 grader 使用简单字符串/正则/NFKC 规范化，后续可接入语义匹配（embedding＋相似度阈值）。
- 冲突处理可参数化：把 conflict_sensitivity 从二值改为可配置实数惩罚权重。
- 更丰富的 arms：加入混合策略（本地 recall + remote tool）或分层记忆（短期/长期）。
- 自动化结果上报：把 report.json 转为 HTML 仪表盘并加入 CI artifact 上传。

作者注
- 文档与实现应保持同步；若评判规则或 grader 行为改动，请同时更新此文档和对应的单元测试。
