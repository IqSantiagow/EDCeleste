from collections.abc import Awaitable, Callable
from typing import Any

from pydantic_ai import ToolReturn

from edceleste.services.models.mcp_tool import McpTool


class ToolRegister:
    """Finds the tools of the given groups. A group is any object whose methods
    are marked with @ToolRegister.register_tool, e.g. PerformGameAction.
    """

    def __init__(self, groups: list[object]) -> None:
        self.groups = groups

    @staticmethod
    def register_tool(
        name: str, readable_name: str, param_name: str
    ) -> Callable[
        [Callable[..., Awaitable[ToolReturn]]],
        Callable[..., Awaitable[ToolReturn]],
    ]:
        """Marks a method as a tool of the LLM by storing the three names on
        the function. Changes nothing else, the method works as before."""

        def tool_decorator(
            func: Callable[..., Awaitable[ToolReturn]],
        ) -> Callable[..., Awaitable[ToolReturn]]:
            marked_function: Any = func
            marked_function.name = name
            marked_function.readable_name = readable_name
            marked_function.param_name = param_name
            return func

        return tool_decorator

    def get_tools(self) -> list[McpTool]:
        """Returns one McpTool for every marked method of every group, the
        method bound to its group. Only the class of a group is scanned, so the
        services a group holds are never taken for tools."""
        tools = []

        for group in self.groups:
            for method_name in dir(type(group)):
                if hasattr(getattr(type(group), method_name), "readable_name"):
                    method = getattr(group, method_name)
                    tools.append(
                        McpTool(
                            method.name,
                            method.readable_name,
                            method.param_name,
                            method,
                        )
                    )
        return tools
