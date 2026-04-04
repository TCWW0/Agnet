"""Terminal chat entry for simple_agent.

Run from project root:
python simple_agent/src/main.py
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from agent import TerminalChatAgent, create_llm_from_env


EXIT_COMMANDS = {"quit", "exit"}


def load_env_file(env_path: Path) -> dict[str, str]:
    """Parse .env and load keys into process environment."""
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue

        loaded[key] = value
        os.environ.setdefault(key, value)

    return loaded


def resolve_env_path() -> Path:
    """Locate simple_agent/.env regardless of current working directory."""
    return Path(__file__).resolve().parents[1] / ".env"


def run_single_turn(agent: TerminalChatAgent, user_text: str, stream: bool) -> None:
    if stream:
        print("Assistant> ", end="", flush=True)
        for chunk in agent.stream_run(user_text):
            print(chunk, end="", flush=True)
        print()
        return

    reply = agent.run(user_text)
    print(f"Assistant> {reply}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="hello_agents terminal chat")
    parser.add_argument("--once", help="只处理一条输入然后退出")
    parser.add_argument(
        "--no-trace",
        action="store_true",
        help="禁用 trace 日志与文件（优先于 .env 配置）",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="启用流式输出",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="LLM 温度参数，默认 0.3",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    env_path = resolve_env_path()
    env_values = load_env_file(env_path)

    llm = create_llm_from_env(env_values, temperature=args.temperature)
    # 读取 trace 配置：CLI --no-trace 优先，其次 .env 中的 TRACE_ENABLED，再默认开启
    def parse_bool(v: str | None) -> bool | None:
        if v is None:
            return None
        vv = str(v).strip().lower()
        if vv in ("1", "true", "yes", "on"):
            return True
        if vv in ("0", "false", "no", "off"):
            return False
        return None

    trace_enabled: bool = True
    if args.no_trace:
        trace_enabled = False
    else:
        te = env_values.get("TRACE_ENABLED") or os.getenv("TRACE_ENABLED")
        parsed = parse_bool(te)
        if parsed is not None:
            trace_enabled = parsed

    # 构建 Config 并传入 Agent
    from hello_agents import Config

    cfg = Config()
    cfg.trace_enabled = trace_enabled
    # 允许通过 TRACE_DIR 指定目录
    trace_dir = env_values.get("TRACE_DIR") or os.getenv("TRACE_DIR")
    if trace_dir:
        cfg.trace_dir = trace_dir

    agent = TerminalChatAgent(llm=llm, config=cfg)

    if args.once:
        run_single_turn(agent, args.once, args.stream)
        return

    print("Simple Agent 已启动。输入 quit 或 exit 退出，输入 /clear 清空会话历史。")

    while True:
        try:
            user_input = input("You> ").strip()
        except EOFError:
            print("\nAssistant> 收到 EOF，退出。")
            break
        except KeyboardInterrupt:
            print("\nAssistant> 已中断，退出。")
            break

        if not user_input:
            continue

        lowered = user_input.lower()
        if lowered in EXIT_COMMANDS:
            print("Assistant> 再见。")
            break

        if lowered == "/clear":
            agent.clear_history()
            print("Assistant> 会话历史已清空。")
            continue

        try:
            run_single_turn(agent, user_input, args.stream)
        except Exception as exc:  # noqa: BLE001 - CLI should not crash on one failed turn.
            print(f"Assistant> 调用失败: {exc}")


if __name__ == "__main__":
    main()
