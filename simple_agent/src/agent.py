"""Simple terminal chat agent based on hello_agents."""

from typing import Mapping, Optional
import os

from hello_agents import HelloAgentsLLM, SimpleAgent, Config


DEFAULT_SYSTEM_PROMPT = """你是一个终端对话助手。
请使用简洁、直接的中文回答用户问题。
当用户输入不明确时，先简短澄清再回答。"""


class TerminalChatAgent(SimpleAgent):
    """不启用工具调用的纯对话 Agent。

    支持传入 `Config` 来控制诸如 `trace_enabled` 的行为。
    """

    def __init__(
        self,
        llm: HelloAgentsLLM,
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None,
    ):
        super().__init__(
            name="TerminalChatAgent",
            llm=llm,
            system_prompt=system_prompt or DEFAULT_SYSTEM_PROMPT,
            config=config,
            enable_tool_calling=False,
        )


def create_llm_from_env(
    env_values: Mapping[str, str],
    temperature: float = 0.3,
) -> HelloAgentsLLM:
    """从 .env 读取到的配置中初始化 HelloAgentsLLM。"""
    model = env_values.get("LLM_MODEL_ID") or os.getenv("LLM_MODEL_ID")
    api_key = env_values.get("LLM_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = env_values.get("LLM_BASE_URL") or os.getenv("LLM_BASE_URL")
    timeout_raw = env_values.get("LLM_TIMEOUT") or os.getenv("LLM_TIMEOUT", "60")
    provider = (env_values.get("LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()

    missing_keys = [
        key
        for key, value in {
            "LLM_MODEL_ID": model,
            "LLM_API_KEY": api_key,
            "LLM_BASE_URL": base_url,
        }.items()
        if not value
    ]
    if missing_keys:
        joined = ", ".join(missing_keys)
        raise ValueError(f"缺少必要配置: {joined}（请检查 simple_agent/.env）")

    try:
        timeout = int(str(timeout_raw).strip())
    except ValueError as exc:
        raise ValueError("LLM_TIMEOUT 必须是整数秒") from exc

    if base_url:
        normalized = base_url.rstrip("/")
        is_ollama_url = "localhost:11434" in normalized or "127.0.0.1:11434" in normalized
        if (provider == "ollama" or is_ollama_url) and not normalized.endswith("/v1"):
            base_url = f"{normalized}/v1"

    return HelloAgentsLLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        temperature=temperature,
    )

        
