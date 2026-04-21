用例类别与设计要点
- Privacy / Redaction
  - 目标：验证当应当屏蔽某些记忆时（敏感信息），系统不会泄露。

建议的用例目录结构与规模
- 自动化生成工具：基于模板批量生成 paraphrase/noise 变体。
- 标注回收策略：为每个 case 指定允许的检索距离/匹配策略，以支持更精细 grader。
字段详解及检索行为
-------------------
下面对每个 JSONL 字段做详尽说明，并指出字段在评测流水线中的作用（是否作为检索输入 / 用于种子注入 / 仅用于打分）。
- `case_id` (string)
  - 含义：本条用例的唯一标识符。
  - 用途：仅用于报告与聚合（不作为检索输入）。示例："cap_name"。
- `suite` (string)
  - 含义：用例所属的测试套（如 `capability`、`regression`、`privacy` 等）。
  - 用途：用于聚合报表（按 suite 汇总）与选择性运行过滤，不影响检索行为。
- `session_id` (string)
  - 含义：表示一组共享上下文/记忆的会话 id。
  - 用途：在 runner/执行器中用作注入与查询的键（调用 `SessionRef(session_id=...)`）。**所有带相同 `session_id` 的用例共享同一 memory 存储桶**，适用于模拟多轮对话或累积记忆场景。
- `agent_route` (string)
  - 含义：指示被测 agent 的实现/路径（例如 `simple`、`react_agent`），用于在多实现间切换。
  - 用途：执行器可据此选择不同的调用逻辑或行为策略（并非记忆检索输入）。

- `user_input` (string)
  - 含义：用户在该用例中发出的查询，等同于真实交互时的 `user` 消息文本。
    - 当执行器在 `hooks` 路径运行时，`AgentMemoryHooks.before_invoke` 会把 `user_input` 作为检索查询传入 `kernel.query(session, user_input, top_k)`（即**作为检索 query**）。
    - 当执行器在 `tools` 路径运行时，Memory 工具（`MemoryToolFacade.recall`）通常也会使用 `user_input` 或执行器构造的子查询作为 `query` 参数。
    - 同时，`user_input` 会作为实际传给 agent/model 的输入（供生成答案）。
- `expected_answer` (string)
  - 含义：本用例的参考正确答案（用于 grader 判定）。
  - 用途：**仅用于评分/判定**（grader 将把模型输出与此字段进行规范化比较以判定 success）。不是直接传入 memory 检索，但用于衡量检索是否有实际价值。
- `expected_memory_snippets` (array of strings)
  - 含义：期望在检索时能被命中（或作为事实来源）的记忆短语/句子。
  - 用途（重要）：在示例 runner 中，这些字符串会在运行前注入到 memory kernel（调用 `kernel.remember_fact(session, text)`）作为“事实存储”。它们同时可作为 grader/metrics 中检索评估的“金标准”，用于计算 `recall@k` / `precision@k`（如果执行器上报检索候选或执行器支持返回检索日志）。**注意**：这些字段并不直接作为模型输入，而是作为 memory 的内容，检索是否命中取决于 `user_input`（或执行器构造的检索 query）与 kernel 的匹配函数。
- `noise_snippets` (array of strings)
  - 含义：与 `expected_memory_snippets` 属于同一 session 下的噪声/误导事实（冲突片段）。
  - 用途：同样在运行前被注入到 kernel（和 expected_memory_snippets 在同一会话桶中），用于模拟记忆污染或历史冲突；若检索返回噪声片段，grader 会记录 conflict 情形并影响 `conflict_sensitivity` 指标（但不会在当前实现中将其作为硬性否决，除非配置为如此）。
- `should_recall` (boolean)
  - 含义：表明本用例是否期望通过 memory 检索来获得答案（即这是一个“记忆依赖”用例）。
  - 用途：用于用例设计与结果解释（例如：若 `should_recall=true` 但 arm A（无记忆）也通过，说明该 case 实际并非严格依赖记忆）。当前 grader 判定以 `expected_answer` 为准（outcome-first），`should_recall` 只是用于记录与分析。

  - 含义：任意标注（例如 `conflict`、`partial`、`privacy`、`paraphrase` 等），便于筛选与聚合。
  - 用途：便于在报表中对特定子类做 drill-down 分析。
额外/可选字段（建议）
- `eval_hint` (string): 测试作者向 grader 提供的额外说明（仅用于人工审阅）。
检索与注入的流程（示意）
   - 对 `expected_memory_snippets` 的每个条目执行 `kernel.remember_fact(session, snippet)`；
2. 在执行 trial 时：
   - 若 arm 使用 `AgentMemoryHooks`（hooks 路径），执行器会先调用 `before_invoke(session, user_input, base_messages)`：内部会根据 policy 调用 `kernel.query(session, user_input, top_k)`，把检索到的记忆合并到 prompt；因此 `user_input` 成为检索 query 的默认来源；
   - 若 arm 使用 Memory 工具（tool path），执行器会显式调用 `MemoryToolFacade.recall(session, query=user_input, top_k=...)` 或者构造自定义的 query（例如抽取实体、key）来调用 recall；
   - agent/model 基于合并后的上下文生成回答，grader 使用 `expected_answer` 进行判定。
注意事项
- 若需要精确比较检索结果，请修改执行器以回传检索候选（或把 `MemoryToolFacade` 的返回写入 trial observation），以便 grader 能计算 recall/precision。
# Memory 评判：测试用例设计说明
日期：2026-04-20
目的

用例格式（JSONL，每行一个 case）
  - user_input: 用户查询/问题（模型输入）
  - expected_answer: 正确答案（字符串）
  - expected_memory_snippets: 列表，期望被检索到的记忆短语/句子
  - noise_snippets: 列表，显式插入到同一 session 的噪声/冲突事实
  - should_recall: 布尔，是否期望通过 memory 检索获得答案
  - tags: 列表，可标注子类型（如 conflict、partial、privacy）

示例（摘自样例文件）
```json
{"case_id":"cap_name","suite":"capability","session_id":"s1","agent_route":"simple","user_input":"what is my name","expected_answer":"your name is alice","expected_memory_snippets":["my name is alice"],"noise_snippets":[],"should_recall":true,"tags":["capability"]}
```

语义与编写规范
- session_id：同一 session 下的 expected_memory_snippets 与 noise_snippets 一起注入 memory，方便模拟真实对话历史。
- expected_memory_snippets：应尽量短小、明确，便于 exact-match 或近似匹配测试（例如姓名、代码片段、偏好设置）。
- noise_snippets：用于模拟记忆污染或冲突事实（例如相同键值的不同答案），验证系统的冲突敏感性。
- should_recall=true：表示期望执行器通过检索来获取答案；若被测系统在无 memory 的 arm（A）上依然正确，则表示该 case 并非严格依赖记忆。

用例类别与设计要点
- Capability（记忆依赖）
  - 目标：当记忆可用时能正确回答；在没有记忆或检索到噪声时应失败或返回未知。
  - 示例：姓名、偏好、历史事实。
- Conflict（冲突）
  - 目标：注入与 expected_answer 冲突的噪声片段，验证 system 在冲突场景下是否被“误导”。
- Partial / Approximate（部分匹配或语义变体）
  - 目标：期望系统能处理近似匹配（例如记忆是复合句，检索结果只匹配子串或语义同义句）。建议加入 paraphrase 变体作为 case 的变体。
- Regression（纯计算/确定题）
  - 目标：验证记忆相关改动不会破坏基础能力（例如数学运算）。
- Privacy / Redaction
  - 目标：验证当应当屏蔽某些记忆时（敏感信息），系统不会泄露。

建议的用例目录结构与规模
- 初始套件：~20–50 条用例，覆盖 capability/regression/conflict/partial。
- 扩展套件：再加入 50–200 条用于压力测试（长文本、多个噪声片段、多轮记忆依赖）。

评分与校验建议
- 每个 case 至少运行 3 次 trial（trials_per_case=3）以估计 pass@k。
- 对 conflict 用例，要记录检索到的噪声是否直接参与生成（需要执行器能上报检索结果或日志）。
- 对于近似匹配用例，可设定匹配模式（exact / fuzzy / embedding）并记录匹配阈值。

如何新增用例并运行
1. 在 frame/evaluation/memory/data/ 下新增 jsonl 行。
2. 运行示例 runner（见 README）：

```bash
/root/agent/.venv/bin/python frame/evaluation/memory/run_memory_eval.py
```

3. 检查 outputs/report.json 与 summary.txt，关注对应 case_id 的结果。

扩展建议
- 自动化生成工具：基于模板批量生成 paraphrase/noise 变体。
- 标注回收策略：为每个 case 指定允许的检索距离/匹配策略，以支持更精细 grader。
