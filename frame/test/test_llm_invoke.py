"""
简单测试LLM的调用是否正常
"""

from frame.core.base_llm import BaseLLM
from frame.core.config import LLMConfig
from frame.core.message import SystemMessage, UserMessage, FunctionMessage
from frame.core.logger import global_logger

class TestLLMInvoke:
    def setup_method(self):
        self.llm_config = LLMConfig.from_env()
        self.llm = BaseLLM(self.llm_config)

    def test_invoke(self):
        messages = [
            SystemMessage("You are a helpful assistant."),
            UserMessage("What is the capital of France?"),
        ]
        payload = self.llm._build_payload(messages)
        global_logger.debug(f"Payload for LLM: {payload}")

        response = self.llm._call_api(payload)
        global_logger.debug(f"Response from LLM: {response}")

        assert response is not None
