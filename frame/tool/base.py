"""定义基础的工具协议，使用OpenAPI规范来描述工具的输入输出结构，以便于工具的创建、调用和验证。
参考链接：https://developers.openai.com/api/reference/python/resources/responses/methods/create
"""
from abc import ABC, abstractmethod
import json
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal, Any

""" 
实例期望的工具定义格式如下：
tools = [
    {
        "type": "function",
        "name": "get_current_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
          "type": "object",
          "properties": {
              "location": {
                  "type": "string",
                  "description": "The city and state, e.g. San Francisco, CA",
              },
              "unit": {
                   "type": "string", 
                   "enum": ["celsius", "fahrenheit"]
              },
          },
          "required": ["location", "unit"],
        }
    }
]
"""

# 一个参数的定义，支持基本类型、枚举、数组和对象等结构
class Property(BaseModel):
    type: Literal["string", "number", "integer", "boolean", "object", "array"]
    description: Optional[str] = None

    enum: Optional[List[str]] = None
    items: Optional["Property"] = None
    properties: Optional[Dict[str, "Property"]] = None
    required: Optional[List[str]] = None

    def to_schema(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "type": self.type
        }

        if self.description:
            result["description"] = self.description

        if self.enum:
            result["enum"] = self.enum

        if self.type == "array" and self.items:
            result["items"] = self.items.to_schema()

        if self.type == "object" and self.properties:
            result["properties"] = {
                k: v.to_schema() for k, v in self.properties.items()
            }

            if self.required:
                result["required"] = self.required

        return result

class ToolParameters(BaseModel):
    type: Literal["object"] = "object"
    properties: Dict[str, Property]
    required: List[str] = Field(default_factory=list)

    def to_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                k: v.to_schema() for k, v in self.properties.items()
            },
            "required": self.required
        }

class ToolDesc(BaseModel):
    type: Literal["function"] = "function"
    name: str
    description: Optional[str] = None
    parameters: ToolParameters

    def to_openai_tool(self):
        result = {
            "type": "function",
            "name": self.name,
            "parameters": self.parameters.to_schema()
        }

        if self.description:
            result["description"] = self.description

        return result

# 工具调用的结果结构
class ToolResponse(BaseModel):
    tool_name: str
    status: Literal["success", "error"]
    output: str
    # 可选的结构化细节字段，供工具返回额外的语义化信息（例如验证错误详情、元数据等）
    details: Optional[Dict[str, Any]] = None

    # 描述工具的输入输出规范，供LLM理解
    @classmethod
    def desc(cls) -> str:
        return (
            "ToolResponse是工具调用的结果结构，包含以下字段：\n"
            "- tool_name: str，表示工具的名称\n"
            "- status: 'success'或'error'，表示工具调用的状态\n"
            "- output: str，表示工具调用的文本化输出或摘要（最好是可供LLM直接消费的自然语言）\n"
            "- details: 可选的结构化详情字段（JSON object），当需要对错误或结果进行语义化说明时使用\n"
            "示例结构：\n"
            "{\n"
            "  \"tool_name\": \"example_tool\",\n"
            "  \"status\": \"success\",\n"
            "  \"output\": \"工具执行成功\",\n"
            "  \"details\": {\"duration_ms\": 12}\n"
            "}"
        )


class ValidationResult(BaseModel):
    """验证返回的语义化结果。"""
    valid: bool
    # 当 valid == False 时，message 应当包含对失败原因的简洁说明，供 LLM 或调用方使用
    message: Optional[str] = None
    # 可选的解析后的参数（例如将字符串转换为数字、规范化路径等），在继续执行时可直接使用
    parsed_params: Optional[Dict[str, Any]] = None
    
class LLMToolCallRequest(BaseModel):
    tool_name: str
    parameters: Dict[str, str]

class BaseTool(ABC):
    name: str
    description: str

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    # 基于OpenAI的工具调用标准，每个工具都需要返回一套自己的输入输出规范，用于后续的注入
    @classmethod
    @abstractmethod
    def desc(cls) -> ToolDesc:
        pass
    
    def execute(self, params: Dict[str, Any]) -> ToolResponse:
        # 参数验证：子类必须返回 ValidationResult
        validation = self.valid_paras(params)
        if not isinstance(validation, ValidationResult):
            return ToolResponse(tool_name=self.name, status="error", output="invalid validation result type", details={"validation": True})

        vresult: ValidationResult = validation
        if not vresult.valid:
            msg = vresult.message or "Invalid parameters"
            return ToolResponse(tool_name=self.name, status="error", output=msg, details={"validation": True})

        # 若验证返回了 parsed_params，则优先使用它们作为执行参数
        exec_params: Dict[str, Any] = params
        if vresult.parsed_params:
            merged = dict(params)
            merged.update(vresult.parsed_params)
            exec_params = merged

        try:
            result = self._execute_impl(exec_params)
            return result
        except Exception as e:
            return ToolResponse(tool_name=self.name, status="error", output=str(e))
        
    @abstractmethod
    def _execute_impl(self, params: Dict[str, Any]) -> ToolResponse:
        pass

    @abstractmethod
    def valid_paras(self, params: Dict[str, Any]) -> ValidationResult:
        """Validate params and return a ValidationResult.

        子类必须返回 `ValidationResult`，可包含 `parsed_params` 以便执行阶段直接使用解析后的参数。
        """
        pass

if __name__ == "__main__":
    tool = ToolDesc(
        name="get_current_weather",
        description="Get weather",
        parameters=ToolParameters(
            properties={
                "location": Property(
                    type="string",
                    description="City name"
                ),
                "unit": Property(
                    type="string",
                    enum=["celsius", "fahrenheit"]
                )
            },
            required=["location", "unit"]
        )
    )
    print(json.dumps(tool.to_openai_tool(), indent=2))