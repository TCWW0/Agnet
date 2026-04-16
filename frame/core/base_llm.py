from __future__ import annotations

from typing import Callable, List, Optional

from openai import OpenAI, Stream
from openai.types.responses import Response, ResponseStreamEvent

from frame.core.config import LLMConfig
from frame.core.llm_orchestrator import LLMInvocationOrchestrator
from frame.core.llm_types import InvocationPolicy, InvocationRequest, RetryPolicy, ToolCallMode
from frame.core.message import LLMResponseFunCallMsg, LLMResponseTextMsg, Message, UserTextMessage
from frame.core.logger import global_logger
from frame.core.openai_adapter import OpenAIResponsesAdapter
from frame.tool.base import BaseTool

# 简单的流式输出示例，实际应该自定制
def on_token(response: str):
    print(response,end="")

# 用于显示暴露出流式的type的各个关键事件类型，避免使用字符串常量，增加可读性和可维护性
class EventType:
    TEXT_DELTA = "response.output_text.delta"
    TEXT_DONE = "response.output_text.done"
    COMPLETED = "response.completed"

class StreamPrinter:
    def __init__(self):
        self.buffer_:str = ""
    
    # 外部可以传入一个buffer_str用于获取最后的完整结果，否则就只是打印流式的结果
    def handle(self, event: ResponseStreamEvent, buffer: list):
        t = getattr(event, "type", None)

        if t == EventType.TEXT_DELTA:
            delta = getattr(event, "delta", None)
            if delta:
                self.buffer_ += delta
                print(delta, end="", flush=True)

        elif t == EventType.TEXT_DONE:
            print()
            buffer.append(self.buffer_)
            self.buffer_ = ""

        elif t == EventType.COMPLETED:
            buffer.append(self.buffer_)
            print("\nResponse completed.")
            self.buffer_ = ""

class BaseLLM:
    def __init__(self, llm_config: LLMConfig, client: Optional[OpenAI] = None):
        self.llm_config_ = llm_config
        self.client_ = client or OpenAI(
            organization=self.llm_config_.organization_,
            api_key=self.llm_config_.api_key_,
            base_url=self.llm_config_.base_url_,
        )
        self.stream_printer_ = StreamPrinter()
        self.adapter_ = OpenAIResponsesAdapter(client=self.client_, model_id=self.llm_config_.model_id_)
        self.orchestrator_ = LLMInvocationOrchestrator(adapter=self.adapter_, logger=global_logger)

    def invoke(self, messages: List[Message], tools: List[BaseTool]) -> List[Message]:
        policy = InvocationPolicy(
            tool_mode=ToolCallMode.AUTO if tools else ToolCallMode.OFF,
            max_tool_rounds=self.llm_config_.max_rounds_,
            retry_policy=RetryPolicy(
                max_attempts=self.llm_config_.retry_attempts_,
                backoff_seconds=self.llm_config_.retry_backoff_seconds_,
            ),
        )
        request = InvocationRequest(messages=messages, tools=tools, policy=policy, stream=False)
        result = self.orchestrator_.invoke(request)
        global_logger.info("LLM response messages=%s, tool_rounds=%s", len(result.emitted_messages), result.total_tool_rounds)
        return result.emitted_messages

    def invoke_with_request(self, request: InvocationRequest):
        return self.orchestrator_.invoke(request)

    # TODO：将生成的output中的所有文本内容提取出来，目前先默认只提取第一条文本内容
    def _extract_response(self, llm_response: Response) -> Optional[LLMResponseTextMsg]:
        if not llm_response.output:
            return None
        
        # 遍历Output中结构
        for item in llm_response.output:
            if getattr(item,"type",None) != "message":
                continue
            # 此时可以进入对应的content
            if getattr(item,"content",None):
                for content_item in item.content:  # type: ignore 这里不加这个注解会发病
                    if getattr(content_item,"type",None) == "output_text":
                        return LLMResponseTextMsg(content=content_item.text) # type: ignore
        return None

    def invoke_streaming(self, messages: List[Message], on_token_callback: Callable[[str], None] = on_token) -> Optional[LLMResponseTextMsg]:
        response: Stream[ResponseStreamEvent] = self.client_.responses.create(
            model=self.llm_config_.model_id_,
            instructions="You are a helpful assistant.",
            input=self._convert_msgs_to_prompt(messages),
            stream=True,
        )
        buffer = []
        for event in response:
            self.stream_printer_.handle(event, buffer)
        return LLMResponseTextMsg(content="".join(buffer))

    def _convert_msgs_to_prompt(self, messages: List[Message]) -> str:
        prompt = ""
        for msg in messages:
            prompt += msg.to_prompt() + "\n"
        return prompt
    
    # 这里的逻辑是想要提取出一次回答的全部业务结果，现在只有文本以及函数调用俩种类型，后续可以添加其他的解析
    # TODO
    def extract_msgs_from_response(self, llm_response: Response) -> List[Message]:
        # 1. 解析Output长度，逐个提取每个单元的内容
        output: List[Message] = []
        if not llm_response.output:
            return output
        for item in llm_response.output:
            if not hasattr(item,"type"):
                continue
            if item.type == "message":
                if hasattr(item,"content"):
                    for content_item in item.content:
                        if hasattr(content_item,"type") and content_item.type == "output_text":
                            output.append(LLMResponseTextMsg(content=content_item.text))
            if item.type == "function_call":
                if hasattr(item, "name") and hasattr(item, "arguments"):
                    output.append(
                        LLMResponseFunCallMsg.from_raw(
                            tool_name=getattr(item, "name", ""),
                            call_id=getattr(item, "call_id", getattr(item, "id", "")),
                            arguments_json=item.arguments,
                        )
                    )

        return output

if __name__ == "__main__":
    user_msg = UserTextMessage(content="请做一下自我介绍")
    llm = BaseLLM(LLMConfig.from_env())
    response = llm.invoke_streaming(messages=[user_msg])
    #print(response.content if response else "No response")