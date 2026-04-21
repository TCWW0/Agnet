本目录包含一个独立的 Memory Kernel 评测示例（不依赖 pytest）。

目标：使用 `InMemoryMemoryKernel` 驱动 `frame.evaluation` 的评测器，生成完整的 `EvalReport`，并把结果写入 `outputs/` 目录便于人工 review。

包含文件：
- `data/memory_eval_cases.sample.jsonl`：示例用例集（JSONL）。
- `executor.py`：实现 `EvalExecutor` 的 `MemoryKernelEvalExecutor`，它会调用 `AgentMemoryHooks` / `MemoryToolFacade` 来模拟不同 arm 的行为。
- `run_memory_eval.py`：独立 runner，负责预置 memory、运行 `evaluate_dataset`，并将 `report.json` 与 `summary.txt` 写入 `outputs/`。

使用方法（在虚拟环境激活后）：
```bash
# 从仓库根目录运行
/root/agent/.venv/bin/python frame/evaluation/memory/run_memory_eval.py
```

输出：
- `outputs/report.json`：完整的 `EvalReport` JSON（包含 trial_results、case_aggregates、arm_suite_summaries、suite_deltas）。
- `outputs/summary.txt`：便于阅读的简短汇总。

此示例旨在快速观察 `InMemoryMemoryKernel` 在 A/B/C 三臂下的行为和指标。
