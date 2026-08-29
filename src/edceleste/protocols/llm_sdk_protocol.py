from typing import AsyncGenerator, Protocol

from edceleste.services.models.message_block import (
    AgentText,
    Thinking,
    ToolCall,
    ToolResult,
)
from edceleste.protocols.tool_protocol import ToolProtocol


class LLMSdkProtocol(Protocol):
    """Protocol for LLM SDK interactions. I think it will be an universal standard."""

    def register_tools(self, tools: list[ToolProtocol]) -> None:
        """Register multiple tools with the LLM SDK protocol."""
        raise NotImplementedError("This method should be implemented by subclasses.")

    def execute_query(
        self, prompt: str
    ) -> AsyncGenerator[AgentText | ToolCall | ToolResult | Thinking, None]:
        """Execute a query using the LLM SDK protocol."""
        raise NotImplementedError("This method should be implemented by subclasses.")
