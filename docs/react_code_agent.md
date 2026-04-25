下面给出一个**面向重写的 ReActCodeAgent 技术方案**。目标是：在你现有 CodeAgent 的基础上，最小破坏性演进为**单循环、可收敛、对弱模型友好**的实现，同时保留你已有的工具体系与执行框架。

---

# 一、设计目标（约束清晰）

1. **单循环（ReAct）驱动**：Thought → Action → Observation → …
2. **短步可纠错**：每一步都能根据工具反馈立即修正
3. **最小工具集优先**：降低决策复杂度
4. **验证内化为规则**：不再独立 phase
5. **可扩展**：后续可加轻量 planning / memory

---

# 二、总体架构

```text
User Input
   ↓
Task Brief Builder
   ↓
ReAct Loop  ──────────────┐
   ↓                      │
LLM (Thought/Action)      │
   ↓                      │
Tool Executor ──→ Observation
   ↓                      │
Message State (Memory) ───┘
   ↓
Finish Checker
   ↓
Final Output
```

---

# 三、核心模块设计

## 1️⃣ ReActLoop（核心执行引擎）

### 职责

* 驱动单循环
* 管理消息状态
* 调用 LLM
* 执行工具
* 控制终止条件

---

### 核心伪代码

```python
class ReActLoop:
    def run(self, user_input: str):
        messages = self._init_messages(user_input)

        for step in range(self.max_steps):
            llm_msgs = self.llm.invoke(
                messages=messages,
                tools=self.tools,
                tool_mode=MANUAL
            )

            messages.extend(llm_msgs)

            tool_calls = extract_tool_calls(llm_msgs)

            if not tool_calls:
                if self._should_finish(llm_msgs, messages):
                    break
                continue

            results = execute_tools(tool_calls)
            messages.extend(results)

        return messages
```

---

## 2️⃣ Message State（统一状态容器）

当前已经有 Message 体系，可以直接复用，但需要强化语义：

### 必须区分的类型

* Thought（text）
* Action（tool call）
* Observation（tool result）

---

### 建议增加字段

```python
class Message:
    role: str
    type: str  # thought / action / observation
    content: str
```

👉 目的：让 LLM 更容易“理解当前上下文状态”

---

## 3️⃣ Prompt 设计（关键）

ReAct 成败 70% 在 prompt。

---

### System Prompt（精简但强约束）

```text
You are a coding agent using a Thought → Action → Observation loop.

At each step:

Thought:
- reason about the next step

Action:
- call a tool if needed

Observation:
- you will see the result

Rules:
- Always think before acting
- Do not skip reasoning
- Use tools instead of guessing
- Prefer minimal edits (apply_patch)
- After modifying code, you MUST run tests
- Do not perform multiple unrelated actions in one step

Finish only when:
- code is correct
- tests pass

Then output: [TASK_COMPLETED]
```

---

### Tool Usage Hints（必须加）

```text
Tool usage:

- read_file(path): read file content
- apply_patch(diff): modify files
- run_tests(path): run tests

Always read before modifying.
```

---

## 4️⃣ Tool System（简化优先）

### 第一阶段（强烈建议）

只保留：

```text
read_file
apply_patch
run_tests
```

---

### 为什么删掉其他工具

| 工具          | 问题   |
| ----------- | ---- |
| search      | 容易乱用 |
| list_dir    | 决策噪音 |
| run_command | 不可控  |

---

## 5️⃣ Tool Executor（你已有，可复用）

直接复用：

```python
_execute_tool_calls()
```

但建议增强：

### 输出标准化

```json
{
  "status": "success" | "error",
  "output": "...",
  "error_type": "...",
}
```

---

## 6️⃣ Finish Checker（必须重写）

你当前：

```python
has_completion_token OR progress_tool
```

这是错误的。

---

### 新逻辑

```python
def should_finish(messages):
    return (
        has_completion_token(messages)
        AND last_run_tests_passed(messages)
    )
```

---

## 7️⃣ Failure Handling（轻量化）

你现在的 failure guidance 是对的，但太“重”。

---

### ReAct 中的做法

不需要复杂 retry 机制，只需要：

```text
If a tool fails:
- read the error
- fix the issue
- try again
```

---

👉 关键点：

**失败 = 下一步 Thought 的输入**

---

# 四、与当前 CodeAgent 的映射关系

| 当前模块         | 新设计      |
| ------------ | -------- |
| ANALYSIS     | 删除       |
| GENERATION   | 融入循环     |
| VERIFICATION | 融入规则     |
| todo         | 可选（后期增强） |
| retry loop   | 删除       |
| tool loop    | 保留       |

---

# 五、最小实现版本（建议第一版）

你不需要一次做到完美，可以先做：

---

## MVP 版本

### 特点

* 无 todo
* 无 planning
* 无 memory
* 单循环 + 3 工具

---

### 文件结构建议

```text
react_code_agent/
├── agent.py          # 主入口
├── react_loop.py     # 核心循环
├── prompt.py         # prompt 模板
├── tools/
│   ├── read_file.py
│   ├── apply_patch.py
│   └── run_tests.py
```

---

# 六、进阶演进路径（你后面会需要）

## 阶段 2：ReAct + Plan（推荐）

引入：

```text
Plan (可修改)
```

结构变为：

```text
Plan → Thought → Action → Observation → Update Plan
```

---

## 阶段 3：加入 Memory

* 失败模式缓存
* 常见修复策略

---

## 阶段 4：多文件 / 多任务支持

---

# 七、关键设计原则（避免走回头路）

## 1️⃣ 不要再引入“强 phase”

否则会退回你现在的问题

---

## 2️⃣ 不要让 LLM 一步做太多事

保持：

> 一步 = 一个 action

---

## 3️⃣ 工具 > 推理

当不确定：

> 优先用工具，而不是“猜”

---

## 4️⃣ 强约束优于自由

弱模型下：

> 限制越多 → 表现越稳定

---

# 八、当前设计的一个核心误区

直接指出：

> 你在试图“用工程结构约束 LLM”

但 ReAct 的思路是：

> **用交互节奏约束 LLM**

---

# 九、建议下一步的实现顺序

1. 删除 phase
2. 写一个 `_run_react_loop`
3. 精简 tool
4. 重写 prompt
5. 改 finish 条件
6. 跑最小 demo

---

# 十、可以重点 review 的点

你在 review 时可以重点看：

* 是否真的实现了“单步决策”
* tool 使用是否减少错误
* 是否 still 出现“无意义循环”
* test 是否真正约束了结束

---
