from typing import Any, Protocol

from pydantic_ai import ToolReturn


class ToolProtocol(Protocol):
    readable_name: str
    param_name: str
    name: str

    async def execute(self, *args: Any, **kwargs: Any) -> ToolReturn: ...
