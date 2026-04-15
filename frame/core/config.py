"""用于统一读取来自环境变量中的配置"""
import os
import dotenv
dotenv.load_dotenv()

class LLMConfig:
    def __init__(
        self,
        model_id: str,
        organization: str,
        api_key: str,
        base_url: str,
        timeout: int,
        max_rounds: int,
        retry_attempts: int = 3,
        retry_backoff_seconds: float = 0.8,
    ):
        self.model_id_ = model_id
        self.organization_ = organization
        self.api_key_ = api_key
        self.base_url_ = base_url
        self.timeout_ = timeout
        self.max_rounds_ = max_rounds
        self.retry_attempts_ = retry_attempts
        self.retry_backoff_seconds_ = retry_backoff_seconds

    @classmethod
    def from_env(cls):
        model_id = os.getenv("LLM_MODEL_ID", "llama3")
        api_key = os.getenv("LLM_API_KEY", "Unknown API Key")
        base_url = os.getenv("LLM_BASE_URL", "https://api.your-llm-provider.com/v1")
        timeout = int(os.getenv("LLM_TIMEOUT", 60))
        max_rounds = int(os.getenv("LLM_MAX_ROUNDS", 5))
        retry_attempts = int(os.getenv("LLM_RETRY_ATTEMPTS", 3))
        retry_backoff_seconds = float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", 0.8))
        origanization = os.getenv("LLM_ORGANIZATION", "")
        return cls(
            model_id,
            origanization,
            api_key,
            base_url,
            timeout,
            max_rounds,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )

llmConfig = LLMConfig.from_env()

class AgentConfig:
    def __init__(self, max_rounds: int):
        self.max_rounds_ = max_rounds

    @classmethod
    def from_env(cls):
        max_rounds = int(os.getenv("AGENT_MAX_ROUNDS", 15))
        return cls(max_rounds)