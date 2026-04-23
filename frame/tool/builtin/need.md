---

# 一、全局约束（适用于所有工具）

1. **工作区限制（Workspace Root）**

   * 所有路径必须位于 `workspace_root` 下。
   * 禁止访问或修改工作区之外的文件。

2. **路径规范**

   * 使用标准化路径（无 `..`、无符号链接逃逸）。
   * 非法路径应直接拒绝。

3. **幂等与可观测性**

   * 工具调用应返回结构化结果（status、message、artifacts）。
   * 对同一输入重复执行，结果应可预期（除执行类工具外）。

4. **原子性**

   * 修改类工具要么完全成功，要么不生效（失败需回滚）。

5. **资源限制**

   * 限制单次读写大小（例如 ≤1MB）。
   * 限制执行时间（例如 ≤10s），防止阻塞。

6. **编码**

   * 默认 UTF-8 文本；二进制文件默认拒绝（除非明确支持）。

---

# 二、工具规范

## 1. read_file

**功能**

* 读取单个文件内容，用于提供上下文。

**输入**

```json
{
  "path": "string",
  "start_line": "int",
  "end_line": "int"
}
```

**输出**

```json
{
  "tool_name": "read_file",
  "status": "success|fail",
  "output": "string"
}
```

**约束**

* 文件必须存在且在工作区内。
* 不进行任何修改操作。

---

## 2. search

**功能**

* 在工作区内进行文本搜索，返回匹配位置。

**输入**

```json
{
  "query": "string",
  "path": "string (optional, default=workspace_root)",
  "max_results": "int (optional)"
}
```

**输出**

```json
{
  "status": "ok|error",
  "results": [
    {
      "path": "string",
      "line": "int",
      "snippet": "string"
    }
  ],
  "message": "string"
}
```

**约束**

* 限制返回条数（如 ≤100）。
* 只读操作，不修改文件。
* 应避免全量扫描导致超时（可分块或提前终止）。

---

## 3. apply_patch（核心工具）

**功能**

* 基于 diff/patch 对文件进行最小化修改。

**输入**

```json
{
  "patch": "string (unified diff format)"
}
```

**输出**

```json
{
  "status": "ok|error",
  "applied_files": ["string"],
  "message": "string"
}
```

**约束**

* patch 必须符合 unified diff 格式。
* 仅允许修改已存在文件或显式创建新文件（需在 patch 中声明）。
* 若任一 hunk 失败 → 整体失败（原子性）。
* 不允许修改工作区外文件。
* 修改前后应保证文件编码一致（UTF-8）。

---

## 4. run_command

**功能**

* 执行受限 shell 命令，用于编译或运行程序。

**输入**

```json
{
  "cmd": "string",
  "timeout_sec": "int (optional)"
}
```

**输出**

```json
{
  "status": "ok|error|timeout",
  "stdout": "string",
  "stderr": "string",
  "exit_code": "int"
}
```

**约束**

* 命令必须在白名单内（如 `g++`, `python`, `make` 等）。
* 禁止网络访问、系统级命令（如 `rm -rf /`）。
* 执行时间必须受限。
* 不保证幂等（允许产生副作用，但应限制在工作区）。

---

## 5. run_tests（推荐）

**功能**

* 执行项目测试套件，返回结果。

**输入**

```json
{
  "framework": "string (optional)",
  "pattern": "string (optional)"
}
```

**输出**

```json
{
  "status": "ok|fail|error",
  "passed": "int",
  "failed": "int",
  "output": "string"
}
```

**约束**

* 本质是对 `run_command` 的封装。
* 测试执行失败不应破坏工作区状态。
* 输出需可供 LLM 分析（保留错误信息）。

---

## 6. git_diff（可选但重要）

**功能**

* 获取当前工作区相对于最近提交的差异。

**输入**

```json
{}
```

**输出**

```json
{
  "status": "ok|error",
  "diff": "string"
}
```

**约束**

* 仅读取，不修改仓库状态。
* diff 长度需限制（可截断）。

---

## 7. git_commit

**功能**

* 提交当前变更，形成可回滚节点。

**输入**

```json
{
  "message": "string"
}
```

**输出**

```json
{
  "status": "ok|error",
  "commit_id": "string"
}
```

**约束**

* 仅提交工作区内变更。
* message 必须非空。
* 不允许自动 push（仅本地操作）。

---

## 8. git_reset

**功能**

* 回滚到指定提交或撤销当前修改。

**输入**

```json
{
  "target": "string (commit id or HEAD)"
}
```

**输出**

```json
{
  "status": "ok|error",
  "message": "string"
}
```

**约束**

* 必须明确目标版本。
* 操作不可部分成功（需保证一致性）。
* 仅作用于工作区。

---

# 三、推荐调用协议（Agent 使用约束）

1. **先读后写**

   * 修改前必须通过 `read_file` 或 `search` 获取上下文。

2. **最小修改原则**

   * 优先使用 `apply_patch`，避免整文件覆盖。

3. **修改后必须验证**

   * 至少执行一次 `run_command` 或 `run_tests`。

4. **失败需迭代**

   * 若执行失败，应根据错误信息重新生成 patch。

5. **阶段性提交**

   * 在稳定状态下调用 `git_commit`。

---

# 四、最小闭环能力定义

一个满足以下流程的系统即为“可用 Code Agent”：

```text
read → patch → apply_patch → run → (fail → retry | success → commit)
```

---

# 五、设计边界（避免过度设计）

当前阶段不建议引入：

* AST 级修改（复杂度过高）
* 多文件依赖分析
* 自动规划（planner）

优先确保：

* patch 可正确应用
* 执行反馈可被利用
* 状态可回滚

---
