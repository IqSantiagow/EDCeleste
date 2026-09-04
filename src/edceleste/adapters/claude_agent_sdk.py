from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, TypeVar

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    SdkMcpTool,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
)
from claude_agent_sdk import UserMessage as SdkUserMessage


from edceleste.protocols.llm_sdk_protocol import LLMSdkProtocol
from edceleste.services.models.message_block import (
    AgentText,
    Thinking,
    ToolCall,
    ToolResult,
)
from edceleste.protocols.tool_protocol import ToolProtocol

T = TypeVar("T")


class NormalizedSdkMcpTool(SdkMcpTool):
    def __init__(
        self,
        readable_name: str,
        param_name: str,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: Callable[[T], Awaitable[dict[str, Any]]],
    ):
        super().__init__(name, description, input_schema, handler)
        self.readable_name = readable_name
        self.param_name = param_name


class ClaudeAgentSDK(LLMSdkProtocol):
    def __init__(self, model: str, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.tools: list[NormalizedSdkMcpTool] = []
        self.mcp_server = None

    def convert_tools(self, tools: list[ToolProtocol]) -> list[NormalizedSdkMcpTool]:
        return [
            NormalizedSdkMcpTool(
                readable_name=tool.readable_name,
                name=tool.name,
                description=tool.description,
                input_schema=tool.parameters,
                handler=tool.execute,
                param_name=tool.param_name,
            )
            for tool in tools
        ]

    def build_options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            mcp_servers={"game": self.mcp_server} if self.mcp_server else {},
            allowed_tools=[f"mcp__game__{tool.name}" for tool in self.tools],
            model=self.model,
            system_prompt=self.system_prompt,
        )

    def register_tools(self, tools: list[ToolProtocol]) -> None:
        self.tools = self.convert_tools(tools)
        self.mcp_server = create_sdk_mcp_server(name="game_actions", tools=self.tools)  # type: ignore

    async def execute_query(
        self, prompt: str
    ) -> AsyncGenerator[AgentText | ToolCall | ToolResult | Thinking, None]:
        async for message in query(prompt=prompt, options=self.build_options()):
            if not isinstance(message, (AssistantMessage, SdkUserMessage)):
                continue
            if isinstance(message.content, str):
                continue
            for block in message.content:
                if isinstance(block, TextBlock):
                    yield AgentText(content=block.text)
                elif isinstance(block, ThinkingBlock):
                    yield Thinking(content=block.thinking)
                elif isinstance(block, ToolUseBlock):
                    yield self._normalize_tool_to_readable_name_and_input(block)
                elif isinstance(block, ToolResultBlock):
                    yield ToolResult(
                        content=block.content, is_error=bool(block.is_error)
                    )

    def _normalize_tool_to_readable_name_and_input(
        self, tool: ToolUseBlock
    ) -> ToolCall:
        tool_name = tool.name.split("__")[
            -1
        ]  # Extract the tool name after the last '__'
        normalized_tool = next((t for t in self.tools if t.name == tool_name), None)
        return ToolCall(
            tool_name=tool_name,
            input=tool.input,
            tool_readable_name=normalized_tool.readable_name
            if normalized_tool is not None
            else tool.name,
            param_name=normalized_tool.param_name
            if normalized_tool is not None
            else None,
        )

    @property
    def get_models(self) -> list[str]:
        return [
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-fable-5",
            "claude-haiku-4-5-20251001",
        ]

    def validate_settings(self, settings: dict[str, str]) -> None:
        model = settings.get("model")
        if model not in self.get_models:
            raise ValueError(f"Invalid model: {model}")
        return None
