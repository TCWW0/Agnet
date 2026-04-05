"""实现简单的LLM适配层，基础意图为通过一个统一接口来提供LLM服务"""
from .config import LLMConfig
from openai import OpenAI
import logging


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = OpenAI(
            api_key=self.config.api_key_,
            base_url=self.config.base_url_,
            timeout=self.config.timeout_
        )
        # TODO: 实现更多的模型适配，当前只需要支持硬编码即可

    # 接受一个字符串输入，返回一个字符串输出
    def invoke(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.config.model_id_,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2048,
            )
            return response.choices[0].message.content # type: ignore
        except Exception as e:
            logging.getLogger("frame.core.llm").exception("LLM 请求失败")
            raise RuntimeError(f"LLM 请求失败: {e}")
        
if __name__ == "__main__":
    from .logging_config import setup_logging
    setup_logging()
    config = LLMConfig.from_env()
    llm_client = LLMClient(config)
    response = llm_client.invoke("请介绍一下你自己。")
    logging.getLogger("frame.core.llm").info(response)
