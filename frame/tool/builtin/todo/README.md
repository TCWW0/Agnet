# TODO Tool (MVP)

该目录提供一个最小可用的 TODO 工具实现，包含：
- `TodoItem` 数据模型与状态枚举
- `TodoStorage` 抽象层
- `JsonTodoStorage` JSON 持久化后端
- `TodoManager`（增删改查）
- `TodoTool`（符合 OpenAI function tool 参数风格）
- `TodoCLI`（终端手工测试）

## 路径规则

存储路径由两部分拼接：
- 环境变量 `TODO_JSON_PATH`（默认 `bin/todo`）
- 外部传入的文件名（例如 `work` 或 `work.json`）

示例：
- `TODO_JSON_PATH=bin/todo`，`filename=work` -> `bin/todo/work.json`
- 未传 `filename` -> `bin/todo/todo.json`

## CLI 用法

```bash
/root/agent/.venv/bin/python -m frame.tool.builtin.todo.cli add "写设计文档" --file work
/root/agent/.venv/bin/python -m frame.tool.builtin.todo.cli list --file work
/root/agent/.venv/bin/python -m frame.tool.builtin.todo.cli get <item_id> --file work
/root/agent/.venv/bin/python -m frame.tool.builtin.todo.cli update <item_id> --status completed --file work
/root/agent/.venv/bin/python -m frame.tool.builtin.todo.cli delete <item_id> --file work
```

## 作为 Tool 使用

```python
from frame.tool.builtin.todo.tool import TodoTool

tool = TodoTool(filename="work")
result = tool.execute({"action": "create", "text": "整理评测报告"})
print(result.status, result.output)
```
