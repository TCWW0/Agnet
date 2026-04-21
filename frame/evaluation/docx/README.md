# Evaluation 文档索引（frame/evaluation/docx）

本目录包含与评测体系相关的设计与用例文档，方便审阅与扩展：

- 20260420-eval-design.md —— 评判体系设计、指标说明、使用说明与实现映射。
- 20260420-memory-testcases.md —— memory 评判专用的测试用例设计规范与示例。

运行示例
- 运行示例 runner：

```bash
/root/agent/.venv/bin/python frame/evaluation/memory/run_memory_eval.py
```

输出位置
- frame/evaluation/memory/outputs/report.json
- frame/evaluation/memory/outputs/summary.txt

后续步骤建议
- 根据本规范扩充 frame/evaluation/memory/data 下的 JSONL 用例，利用 runner 迭代调优 grader 策略。
