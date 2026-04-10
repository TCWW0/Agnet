"""实现简单的LLM适配层，基础意图为通过一个统一接口来提供LLM服务"""
from frame.core.config import LLMConfig
from openai import OpenAI
import logging
import random
import time
from typing import Any, Optional

class LLMClient:
    def __init__(self, config: LLMConfig, client: Optional[Any] = None):
        self.config = config
        self.client = client or OpenAI(
            organization=self.config.origanization_,
            api_key=self.config.api_key_,
            base_url=self.config.base_url_,
            timeout=self.config.timeout_
        )
        self.retry_attempts = max(1, int(getattr(self.config, "retry_attempts_", 3)))
        self.retry_backoff_seconds = max(0.0, float(getattr(self.config, "retry_backoff_seconds_", 0.8)))
        # TODO: 实现更多的模型适配，当前只需要支持硬编码即可

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if isinstance(status_code, int) and status_code in {408, 409, 429, 500, 502, 503, 504}:
            return True

        resp = getattr(exc, "response", None)
        resp_status_code = getattr(resp, "status_code", None)
        if isinstance(resp_status_code, int) and resp_status_code in {408, 409, 429, 500, 502, 503, 504}:
            return True

        # 对 OpenAI SDK 常见的临时错误名进行兜底识别，避免版本差异导致漏判
        retryable_names = {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}
        return exc.__class__.__name__ in retryable_names

    # 接受一个字符串输入，返回一个字符串输出
    def invoke(self, prompt: str) -> str:
        logger = logging.getLogger("frame.core.llm")
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model_id_,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=2048,
                )
                content = response.choices[0].message.content # type: ignore
                if isinstance(content, str):
                    return content
                if content is None:
                    return ""
                return str(content)
            except Exception as e:
                last_error = e
                retryable = self._is_retryable_error(e)
                is_last = attempt >= self.retry_attempts

                if (not retryable) or is_last:
                    logger.exception(
                        "LLM 请求失败，attempt=%d/%d，retryable=%s",
                        attempt,
                        self.retry_attempts,
                        retryable,
                    )
                    raise RuntimeError(f"LLM 请求失败: {e}")

                # 指数退避 + 少量抖动，降低瞬时故障或拥塞时的放大效应
                base_wait = self.retry_backoff_seconds * (2 ** (attempt - 1))
                wait_seconds = min(base_wait, 8.0) + random.uniform(0, 0.2)
                logger.warning(
                    "LLM 请求失败，准备重试 attempt=%d/%d，等待 %.2fs，错误=%s",
                    attempt,
                    self.retry_attempts,
                    wait_seconds,
                    str(e),
                )
                time.sleep(wait_seconds)

        raise RuntimeError(f"LLM 请求失败: {last_error}")
        
if __name__ == "__main__":
    config = LLMConfig.from_env()
    llm_client = LLMClient(config)
    response = llm_client.invoke("请介绍一下你自己。")
    print("LLM 响应:", response)