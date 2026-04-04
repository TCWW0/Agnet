"""用于统一读取来自环境变量中的配置"""
import os
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

class LLMConfig:
    def __init__(self, model_id: str, api_key: str, base_url: str, timeout: int,max_rounds: int):
        self.model_id_ = model_id
        self.api_key_ = api_key
        self.base_url_ = base_url
        self.timeout_ = timeout
        self.max_rounds_ = max_rounds

    @classmethod
    def from_env(cls):
        model_id = os.getenv("LLM_MODEL_ID", "llama3")
        api_key = os.getenv("LLM_API_KEY", "Unknown API Key")
        base_url = os.getenv("LLM_BASE_URL", "https://api.your-llm-provider.com/v1")
        timeout = int(os.getenv("LLM_TIMEOUT", 60))
        max_rounds = int(os.getenv("LLM_MAX_ROUNDS", 5))
        return cls(model_id, api_key, base_url, timeout, max_rounds)

llmConfig = LLMConfig.from_env()

class AgentConfig:
    def __init__(self, max_rounds: int):
        self.max_rounds_ = max_rounds

    @classmethod
    def from_env(cls):
        max_rounds = int(os.getenv("AGENT_MAX_ROUNDS", 5))
        return cls(max_rounds)