# Simple Terminal Agent (hello_agents)

这是一个基于 `hello_agents` 的终端持续对话示例，入口位于 `src/main.py`。

运行方法（在仓库根目录）：

```bash
python simple_agent/src/main.py
```

单次调用测试：

```bash
python simple_agent/src/main.py --once "你好"
```

可选参数：

```bash
python simple_agent/src/main.py --stream
python simple_agent/src/main.py --temperature 0.2
```

说明：
- 自动读取 `simple_agent/.env`（`LLM_MODEL_ID`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_TIMEOUT`）
- 输入 `quit` 或 `exit` 退出
- 输入 `/clear` 清空当前会话历史