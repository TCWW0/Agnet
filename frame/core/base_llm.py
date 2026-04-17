from __future__ import annotations

from typing import List, Optional

from openai import OpenAI
from openai.types.responses import Response

from frame.core.config import LLMConfig
from frame.core.llm_orchestrator import LLMInvocationOrchestrator
from frame.core.llm_types import InvocationPolicy, InvocationRequest, RetryPolicy, TextDeltaCallback, ToolCallMode
from frame.core.message import LLMResponseFunCallMsg, LLMResponseTextMsg, Message, UserTextMessage
from frame.core.logger import global_logger
from frame.core.openai_adapter import OpenAIResponsesAdapter
from frame.core.text_emitter import DispatchMode, QueueFullStrategy, TextEmitter, default_text_callback
from frame.tool.base import BaseTool

class BaseLLM:
    def __init__(self, llm_config: LLMConfig, client: Optional[OpenAI] = None):
        self.llm_config_ = llm_config
        self.client_ = client or OpenAI(
            organization=self.llm_config_.organization_,
            api_key=self.llm_config_.api_key_,
            base_url=self.llm_config_.base_url_,
        )
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

    def invoke_streaming(
        self,
        messages: List[Message],
        tools: Optional[List[BaseTool]] = None,
        on_token_callback: TextDeltaCallback = default_text_callback,
    ) -> List[Message]:
        using_tools = tools or []
        policy = InvocationPolicy(
            tool_mode=ToolCallMode.AUTO if using_tools else ToolCallMode.OFF,
            max_tool_rounds=self.llm_config_.max_rounds_,
            retry_policy=RetryPolicy(
                max_attempts=self.llm_config_.retry_attempts_,
                backoff_seconds=self.llm_config_.retry_backoff_seconds_,
            ),
        )

        request = InvocationRequest(
            messages=messages,
            tools=using_tools,
            policy=policy,
            stream=True,
        )

        emitter = TextEmitter(
            callback=on_token_callback,
            dispatch_mode=DispatchMode.PER_CHAR,
            max_queue_size=1024,
            on_queue_full=QueueFullStrategy.BLOCK,
            logger=global_logger,
        )
        try:
            result = self.orchestrator_.invoke_streaming(request=request, on_text_delta=emitter.emit)
        finally:
            emitter.close()

        global_logger.info(
            "LLM stream response messages=%s, tool_rounds=%s",
            len(result.emitted_messages),
            result.total_tool_rounds,
        )

        return result.emitted_messages

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