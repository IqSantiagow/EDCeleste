from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal
import lmstudio as lms
from lmstudio._sdk_models import LlmPredictionFragment, ToolCallRequestData

from edceleste.protocols.llm_sdk_protocol import LLMSdkProtocol
from edceleste.services.models.message_block import (
    AgentText,
    Thinking,
    ToolCall,
    ToolResult,
)
from edceleste.protocols.tool_protocol import ToolProtocol


@dataclass(frozen=True, slots=True, kw_only=True)
class DecoratedToolFunctionDef(lms.ToolFunctionDef):
    readable_name: str
    param_name: str


class LMStudioSDK(LLMSdkProtocol):
    def __init__(self, model: str, system_prompt: str):
        self.model = model
        self.system_prompt = system_prompt
        self.tools: list[DecoratedToolFunctionDef] = []

    def register_tools(self, tools: list[ToolProtocol]) -> None:
        self.tools = [
            DecoratedToolFunctionDef(
                readable_name=tool.readable_name,
                name=tool.name,
                description=tool.description,
                param_name=tool.param_name,
                parameters=self.to_lms_fun_params(tool.parameters),
                implementation=tool.execute,
            )
            for tool in tools
        ]

    async def execute_query(
        self, prompt: str
    ) -> AsyncGenerator[AgentText | ToolCall | ToolResult | Thinking, None]:
        events: list[AgentText | ToolCall | ToolResult | Thinking] = []
        final_response: str = ""

        def on_prediction_fragment(fragment: LlmPredictionFragment, _: int) -> None:
            nonlocal final_response
            if fragment.reasoning_type == "none" and fragment.content:
                final_response += fragment.content

        def on_message(message: lms.AssistantResponse | lms.ToolResultMessage):
            if isinstance(message, lms.AssistantResponse):
                for content_part in message.content:
                    if isinstance(content_part, ToolCallRequestData):
                        events.append(
                            self.search_for_tool_in_registered_tools_by_tool_call_request(
                                content_part.tool_call_request
                            )
                        )
            elif isinstance(message, lms.ToolResultMessage):
                for content_part in message.content:
                    if isinstance(content_part, lms.ToolCallResultData):
                        events.append(ToolResult(content=content_part.content))

        async with lms.AsyncClient() as client:
            model = await client.llm.model(self.model)
            await model.act(
                prompt,
                on_message=on_message,
                tools=self.tools,
                on_prediction_fragment=on_prediction_fragment,
            )
        for event in events:
            yield event

        yield AgentText(content=final_response)

    @property
    def get_models(self) -> list[str]:
        return [model.get_info().model_key for model in lms.list_loaded_models("llm")]

    def validate_settings(self, settings: dict[str, str]) -> None:
        if settings.get("model") not in self.get_models:
            raise ValueError(
                f"Invalid model: {settings.get('model')}. Load this model first"
            )

    def to_lms_fun_params(self, args: dict[str, Any]) -> dict[str, Any]:
        parameter_type_map: dict[str, type] = {
            "string": str,
            "number": float,
            "boolean": bool,
            "integer": int,
            "array": list,
            "object": object,
        }

        params = dict()
        properties = args.get("properties", {})
        if not properties:
            raise RuntimeError(f"Missing 'properties' in argument {args}")
        for key in properties:
            if not isinstance(properties[key], dict):
                raise RuntimeError(
                    f"Revice to_lms_fun_params function with argument {args}"
                )
            if "enum" in properties[key]:
                params[key] = Literal[tuple(properties[key]["enum"])]
                continue

            params[key] = parameter_type_map[properties[key]["type"]]
        return params

    def search_for_tool_in_registered_tools_by_tool_call_request(
        self, tool_call_request: "lms.ToolCallRequest"
    ) -> ToolCall:
        found_tool = next(
            (tool for tool in self.tools if tool.name == tool_call_request.name), None
        )
        return ToolCall(
            input=dict(tool_call_request.arguments or {}),
            tool_name=tool_call_request.name,
            tool_readable_name=found_tool.readable_name
            if found_tool
            else tool_call_request.name,
            param_name=found_tool.param_name if found_tool else None,
        )
