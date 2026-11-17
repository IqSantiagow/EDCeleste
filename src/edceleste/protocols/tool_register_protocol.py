from typing import Protocol

from edceleste.services.models.mcp_tool import McpTool


class ToolRegisterProtocol(Protocol):
    def get_tools(self) -> list[McpTool]:
        """Every tool the LLM can call. Empty list when none is registered."""
        ...
