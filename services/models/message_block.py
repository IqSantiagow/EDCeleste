from dataclasses import dataclass
from typing import Any


@dataclass
class AgentText:
    """Represents a response from the agent.

    This can be partial text or a complete response.
    """

    content: str


@dataclass
class ToolCall:
    """Represents a response from a tool call."""

    tool_readable_name: str
    tool_name: str
    param_name: str | None
    input: dict[str, Any]


@dataclass
class ToolResult:
    """Represents a response from a tool."""

    content: str | list[dict[str, Any]] | None
    is_error: bool = False


@dataclass
class Thinking:
    """Represents a thinking response from the agent."""

    content: str


@dataclass
class AgentFullResponse:
    """Represents a full response from the agent.

    It includes text, tool calls, and tool results.
    """

    content: str
    tool_calls: list[ToolCall]
    tool_results: list[ToolResult]


@dataclass
class UserMessage:
    """Represents a message from the user."""

    content: str


@dataclass
class SystemMessage:
    """Represents a message from the system."""

    content: str
