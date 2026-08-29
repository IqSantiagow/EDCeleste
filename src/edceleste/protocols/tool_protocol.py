from typing import Any, Protocol


class ToolProtocol(Protocol):
    readable_name: str
    param_name: str
    name: str
    description: str
    parameters: dict[str, Any]

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("This method should be implemented by subclasses.")
