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

    def register_tools(self, tools: list[ToolProtocol]) -> None: ...

    def execute_query(
        self, prompt: str
    ) -> AsyncGenerator[AgentText | ToolCall | ToolResult | Thinking, None]: ...

    @property
    def get_models(self) -> list[str]: ...

    def validate_settings(self, settings: dict[str, str]) -> None: ...
