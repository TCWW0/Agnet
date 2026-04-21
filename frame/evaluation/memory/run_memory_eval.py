from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import sys
from pathlib import Path as _Path

# Ensure repository root is on sys.path so `frame` package imports work when running
# this script directly.
_ROOT = _Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from frame.evaluation.dataset import load_eval_cases
from frame.evaluation.models import EvalConfig
from frame.evaluation.harness import evaluate_dataset

from frame.memory.base import InMemoryMemoryKernel, SessionRef
from frame.evaluation.memory.executor import MemoryKernelEvalExecutor


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "memory_eval_cases.sample.jsonl"
OUTPUT_DIR = BASE_DIR / "outputs"

EXPLANATION_TEXT = """字段到流水线使用的详细映射（详尽）

总体：下面说明 EvalCase 的每个字段在评测流水线中的角色 —— 是否会被注入到 memory、是否会作为检索 query、是否仅用于打分或聚合，以及在 runner/执行器中的具体调用点。

case_id: 用作本条用例的唯一标识，用于报告/聚合/追踪。不会作为检索输入。
suite: 用于分组与聚合（如 capability / regression），不参与检索逻辑。
session_id: 作为 memory kernel 的存储桶键。在 runner 的 seed 阶段，expected_memory_snippets 与 noise_snippets 会以 kernel.remember_fact(SessionRef(session_id), text) 注入到该 session 的 memory 中。AgentMemoryHooks 与 MemoryToolFacade 在检索时会以此 session_id 进行 load/query/recall。
agent_route: 用于选择不同 agent 实现或执行逻辑（执行器可根据该值变更调用路径）；不直接参与检索。
user_input: 主查询文本。若使用 hooks 路径，AgentMemoryHooks.before_invoke 内会调用 kernel.query(session, user_input, top_k)；若使用工具路径，MemoryToolFacade.recall(session, query=user_input, top_k) 通常以此为默认查询。user_input 同时作为传递给模型的 prompt 输入，执行器也可能基于它构造更精细的检索 query（如抽取实体或 key）。
expected_answer: 仅用于 grader 判定（对照模型输出以判断正确性）。不会在 seed 阶段自动注入到 memory（除非测试用例作者另行添加）。
expected_memory_snippets: 在 seed 阶段会注入到 memory（调用 kernel.remember_fact），作为检索的“金标准”。只有当 kernel.query 返回这些片段（或包含这些片段）时，模型才会接收到它们；同时用于计算 recall@k / precision@k 指标。
noise_snippets: 同样在 seed 阶段注入，用来模拟记忆污染或冲突事实。若检索返回噪声片段，会影响 recalled_contents 与 conflict_sensitivity 指标（但默认实现将其作为可分析的软信号，而非直接否决）。
should_recall: 设计/分析提示，表明该用例期望通过 memory 检索获得答案。执行器/runner 不强制执行，仅用于结果解释（若 should_recall=true 但 A-arm 也通过，说明该用例并非严格依赖 memory）。
tags: 元标注字段，用于报告过滤与 drill-down 分析，不参与检索。
answer_match_mode: 控制 grader 如何匹配答案（exact / contains / regex），影响成功判定。

流水线要点：
- Seed：runner 会先对所有用例执行注入（seed_kernel_from_cases），把 expected_memory_snippets 与 noise_snippets 注入到各自的 session 中。
- Hooks 路径：AgentMemoryHooks.before_invoke 会先 load_recent(session, max_history_items)，若 policy.enable_retrieval 为 True，再执行 kernel.query(session, user_input, top_k)，将检索到的 Message 合并到 prompt，并进行去重后传给模型。
- Tools 路径：MemoryToolFacade.recall(session, query, top_k) 会调用 kernel.query 并以字符串列表返回；该调用计为一次工具调用（TrialObservation.n_toolcalls）。
- Executor：执行器需在 TrialObservation.recalled_contents 中记录实际提供给模型的记忆文本（以便 grader 计算 recall/precision 并做冲突分析）。
- Grader：grade_trial(case, observation) 使用模型输出（observation.answer_text）与 recalled_contents 对照 expected_answer 与 expected_memory_snippets 来计算 grader_score_det、recall@k、precision@k、memory_usage_score、conflict_sensitivity 等，并根据 outcome-first 策略决定 success。

输出写入位置（runner 行为）:
- summary.txt 会在顶部附加此文本块，便于人工快速理解各列含义与字段使用方式。
- report.json 会包含 _explanations_text（完整文本）与 _explanations（字段->简短描述的字典），便于自动化解析或展示。
"""

EXPLANATIONS = {
    "case_id": "唯一用例 ID（仅用于报告/聚合/追踪）",
    "suite": "用例套（capability/regression），用于分组和汇总统计",
    "session_id": "memory 存储桶键；seed 阶段用于注入 expected/noise snippets；检索时作为 kernel.query 的 session",
    "agent_route": "选择不同 agent/执行路径的标识（不直接参与检索）",
    "user_input": "主查询文本；作为 kernel.query / MemoryToolFacade.recall 的默认 query，同时为模型输入",
    "expected_answer": "grader 的参考答案，仅用于评分，不直接注入 memory",
    "expected_memory_snippets": "在 seed 阶段注入到 kernel（gold memory）；用于 recall/precision 计算，只有被检索到时才提供给模型",
    "noise_snippets": "在 seed 阶段注入以模拟冲突；若检索返回则影响 conflict_sensitivity",
    "should_recall": "设计提示字段，表明期望记忆被使用（仅用于分析/解释）",
    "tags": "用于分类/过滤/分组分析",
    "answer_match_mode": "控制 grader 答案匹配模式（exact/contains/regex）",
    "TrialResult.recalled_contents": "执行器实际提供给模型的记忆片段（用于 recall/precision 与冲突分析）",
}

SUMMARY_METRICS_EXPLANATION = """指标字段说明（用于 summary 中的两部分）

Arm Suite Summaries 字段说明：
- success_rate: 在该 suite+arm 下所有 trial 的成功率均值（0.0–1.0）。表示总体正确率或通过率。
- pass@1: 对每个 case 计算的 pass@1（在 1 次尝试内至少成功一次的概率），然后对所有 case 求平均。
- pass@k: 对每个 case 计算的 pass@k（k 为配置中的 pass_k），表示在 k 次尝试内至少成功一次的概率，结果为 case 级别的平均值。
- mean_tokens: trial 级别的平均 `total_tokens`（用于估计 token 成本；示例中为模拟值，真实接入 LLM 时为实际 token）。
- mean_latency_ms: trial 级别的平均 `latency_ms`（毫秒），表示响应延迟的平均值。

Suite Deltas (B vs A) 字段说明：
- delta_success_b_vs_a: arm B 的 success_rate 减去 arm A 的 success_rate（B - A）。正值表示 B（启用 memory/检索）相对 A（无 memory）有提升。
- delta_success_c_vs_b: arm C 的 success_rate 减去 arm B 的 success_rate（C - B）。
- latency_ratio_b_vs_a: mean_latency_ms(B) 除以 mean_latency_ms(A)。若分母为 0，使用安全除法返回 0。值>1 表示 B 的平均延迟更高。
- token_ratio_b_vs_a: mean_total_tokens(B) 除以 mean_total_tokens(A)。值>1 表示 B 消耗更多 token。

注意：summary 中展示的 mean 字段在文本中可能做了四舍五入显示（例如显示为 0.0），而 ratio/ delta 使用精确数值计算并显示更多精度，因此可能出现表面为 0.0 但 ratio 大于 1 的情况。
"""


def seed_kernel_from_cases(kernel: InMemoryMemoryKernel, cases):
    """Pre-populate kernel facts for each case so retrieval can succeed/fail deterministically."""
    from frame.memory.base import InMemoryMemoryKernel

    for case in cases:
        session = SessionRef(session_id=case.session_id)
        # store expected memory snippets as facts
        for snippet in case.expected_memory_snippets:
            if snippet and hasattr(kernel, "remember_fact"):
                kernel.remember_fact(session, snippet)
        # store noise snippets as facts as well
        for snippet in case.noise_snippets:
            if snippet and hasattr(kernel, "remember_fact"):
                kernel.remember_fact(session, snippet)


def write_report_outputs(report, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    summary_path = out_dir / "summary.txt"

    # Dump full JSON (use pydantic model_dump to get serializable dict)
    try:
        payload = report.model_dump()
    except Exception:
        # fallback to naive conversion
        payload = report.__dict__

    # Attach explanations / metadata to the JSON payload for easier programmatic consumption
    try:
        payload["_explanations"] = EXPLANATIONS
        payload["_explanations_text"] = EXPLANATION_TEXT
        payload["_metrics_explanations_text"] = SUMMARY_METRICS_EXPLANATION
        payload["_metrics_explanations"] = {
            "success_rate": "Trial 级别 success 布尔均值，表示总体成功率（0-1）",
            "pass_at_1": "Case 级 pass@1 的平均值（在 1 次尝试内至少成功一次）",
            "pass_at_k": "Case 级 pass@k 的平均值（k 为配置中的 pass_k）",
            "mean_tokens": "平均 total_tokens（模拟或真实 token 消耗）",
            "mean_latency_ms": "平均 latency_ms（毫秒）",
            "delta_success_b_vs_a": "B.arm success_rate - A.arm success_rate（表示记忆带来的成功率提升）",
            "delta_success_c_vs_b": "C.arm success_rate - B.arm success_rate",
            "latency_ratio_b_vs_a": "mean_latency_ms(B) / mean_latency_ms(A)（若分母为0返回0）",
            "token_ratio_b_vs_a": "mean_total_tokens(B) / mean_total_tokens(A)",
        }
    except Exception:
        # ignore if payload is not a dict-like
        pass

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, indent=2, ensure_ascii=False)

    # Human readable summary (prepend field explanations for reviewers)
    lines = []
    # Add verbose field->pipeline mapping
    # lines.append("=== FIELD TO PIPELINE MAPPING ===")
    # for ex_line in EXPLANATION_TEXT.splitlines():
    #     lines.append(ex_line)
    # lines.append("")

    # Add short field explanations
    # lines.append("=== SHORT FIELD DESCRIPTIONS ===")
    # for k, v in EXPLANATIONS.items():
    #     lines.append(f"{k}: {v}")
    # lines.append("")

    # Add metrics explanations
    lines.append("=== METRICS EXPLANATION ===")
    for m_line in SUMMARY_METRICS_EXPLANATION.splitlines():
        lines.append(m_line)
    lines.append("")

    # Basic run metadata
    lines.append(f"Eval ID: {report.eval_id}")
    lines.append(f"Run at: {report.run_at}")
    lines.append("")

    # Arm Suite summaries
    lines.append("--- Arm Suite Summaries ---")
    for s in report.arm_suite_summaries:
        lines.append(
            f"suite={s.suite.value} arm={s.arm.value} cases={s.case_count} trials={s.trial_count} success_rate={s.success_rate:.3f} pass@1={s.pass_at_1:.3f} pass@k={s.pass_at_k:.3f} mean_tokens={s.mean_total_tokens:.1f} mean_latency_ms={s.mean_latency_ms:.1f}"
        )

    lines.append("")
    lines.append("--- Suite Deltas (B vs A) ---")
    for d in report.suite_deltas:
        lines.append(
            f"suite={d.suite.value} delta_success_b_vs_a={d.delta_success_b_vs_a:.3f} delta_success_c_vs_b={d.delta_success_c_vs_b:.3f} latency_ratio_b_vs_a={d.latency_ratio_b_vs_a:.3f} token_ratio_b_vs_a={d.token_ratio_b_vs_a:.3f}"
        )

    with summary_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    # Also produce a simple HTML view for quick visualization while keeping original JSON
    try:
        import html as _html

        html_path = out_dir / "report.html"
        json_text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        json_escaped = _html.escape(json_text)

        html_parts = []
        html_parts.append("<!doctype html>")
        html_parts.append("<html lang='en'><head><meta charset='utf-8'><title>Eval Report</title><style>body{font-family:Arial,Helvetica,sans-serif;margin:20px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px}th{background:#f4f4f4}</style></head><body>")
        html_parts.append(f"<h1>Eval Report</h1>")
        html_parts.append(f"<p><strong>Eval ID:</strong> {_html.escape(str(report.eval_id))}</p>")
        html_parts.append(f"<p><strong>Run at:</strong> {_html.escape(str(report.run_at))}</p>")

        html_parts.append("<h2>Field Mapping</h2>")
        html_parts.append("<pre>" + _html.escape(EXPLANATION_TEXT) + "</pre>")

        html_parts.append("<h3>Short Field Descriptions</h3>")
        html_parts.append("<ul>")
        for k, v in EXPLANATIONS.items():
            html_parts.append(f"<li><strong>{_html.escape(k)}</strong>: {_html.escape(v)}</li>")
        html_parts.append("</ul>")

        html_parts.append("<h2>Metrics Explanation</h2>")
        html_parts.append("<pre>" + _html.escape(SUMMARY_METRICS_EXPLANATION) + "</pre>")

        # Arm Suite Summaries table
        html_parts.append("<h2>Arm Suite Summaries</h2>")
        html_parts.append("<table><thead><tr><th>Suite</th><th>Arm</th><th>Cases</th><th>Trials</th><th>Success Rate</th><th>Pass@1</th><th>Pass@k</th><th>Mean Tokens</th><th>Mean Latency (ms)</th></tr></thead><tbody>")
        for s in report.arm_suite_summaries:
            html_parts.append("<tr>")
            html_parts.append(f"<td>{_html.escape(s.suite.value)}</td>")
            html_parts.append(f"<td>{_html.escape(s.arm.value)}</td>")
            html_parts.append(f"<td>{s.case_count}</td>")
            html_parts.append(f"<td>{s.trial_count}</td>")
            html_parts.append(f"<td>{s.success_rate:.3f}</td>")
            html_parts.append(f"<td>{s.pass_at_1:.3f}</td>")
            html_parts.append(f"<td>{s.pass_at_k:.3f}</td>")
            html_parts.append(f"<td>{s.mean_total_tokens:.1f}</td>")
            html_parts.append(f"<td>{s.mean_latency_ms:.1f}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody></table>")

        # Suite deltas
        html_parts.append("<h2>Suite Deltas (B vs A)</h2>")
        html_parts.append("<table><thead><tr><th>Suite</th><th>Delta Success B vs A</th><th>Delta Success C vs B</th><th>Latency Ratio B vs A</th><th>Token Ratio B vs A</th></tr></thead><tbody>")
        for d in report.suite_deltas:
            html_parts.append("<tr>")
            html_parts.append(f"<td>{_html.escape(d.suite.value)}</td>")
            html_parts.append(f"<td>{d.delta_success_b_vs_a:.3f}</td>")
            html_parts.append(f"<td>{d.delta_success_c_vs_b:.3f}</td>")
            html_parts.append(f"<td>{d.latency_ratio_b_vs_a:.3f}</td>")
            html_parts.append(f"<td>{d.token_ratio_b_vs_a:.3f}</td>")
            html_parts.append("</tr>")
        html_parts.append("</tbody></table>")

        html_parts.append("<h2>Full JSON Report</h2>")
        html_parts.append(f"<pre>{json_escaped}</pre>")
        html_parts.append(f"<p>Original JSON: <a href='report.json'>report.json</a></p>")
        html_parts.append("</body></html>")

        with html_path.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(html_parts))
    except Exception:
        # Best-effort HTML generation; ignore errors so JSON/summary still get written
        pass


def main() -> None:
    print("Loading cases from:", DATA_PATH)
    cases = load_eval_cases(str(DATA_PATH))

    kernel = InMemoryMemoryKernel()
    seed_kernel_from_cases(kernel, cases)

    executor = MemoryKernelEvalExecutor(kernel)

    config = EvalConfig(name="inmemory-kernel-eval", dataset_path=str(DATA_PATH), trials_per_case=3, pass_k=3)

    print("Running evaluation...")
    report = evaluate_dataset(cases=cases, config=config, executor=executor, git_sha="local", model_name="inmemory-kernel")

    out_dir = OUTPUT_DIR
    write_report_outputs(report, out_dir)

    print(f"Done. Outputs written to: {out_dir}")


if __name__ == "__main__":
    main()
