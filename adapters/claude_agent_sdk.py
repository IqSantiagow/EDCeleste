from collections.abc import AsyncGenerator

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

from adapters.llm_sdk_protocol import LLMSdkProtocol
from adapters.message_block import (
    AgentText,
    Thinking,
    ToolCall,
    ToolResult,
)
from adapters.tool_protocol import ToolProtocol


class ClaudeAgentSDK(LLMSdkProtocol):
    def __init__(self, model: str, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.tools: list[SdkMcpTool] = []

    def convert_tools(self, tools: list[ToolProtocol]) -> list[SdkMcpTool]:
        """Convert a list of ToolProtocol instances to a list of SdkMcpTool instances."""
        return [
            SdkMcpTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.parameters,
                handler=tool.execute,
            )
            for tool in tools
        ]

    def build_options(self) -> ClaudeAgentOptions:
        mcp_server = create_sdk_mcp_server(name="game_actions", tools=self.tools)
        return ClaudeAgentOptions(
            mcp_servers={"game": mcp_server},
            allowed_tools=[f"mcp__game__{tool.name}" for tool in self.tools],
            model=self.model,
            system_prompt=self.system_prompt,
        )

    def register_tools(self, tools: list[ToolProtocol]) -> None:
        """Register multiple tools with the LLM SDK protocol."""
        self.tools = self.convert_tools(tools)

    async def execute_query(
        self, prompt: str
    ) -> AsyncGenerator[AgentText | ToolCall | ToolResult | Thinking, None]:
        """Execute a query using the LLM SDK protocol."""
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
                    yield ToolCall(tool_name=block.name, input=block.input)
                elif isinstance(block, ToolResultBlock):
                    yield ToolResult(
                        content=block.content, is_error=bool(block.is_error)
                    )
