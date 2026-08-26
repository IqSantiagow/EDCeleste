from typing import Any, Protocol


class ToolProtocol(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("This method should be implemented by subclasses.")
