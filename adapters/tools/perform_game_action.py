from protocols.tool_protocol import ToolProtocol
from adapters.tools.tool_result import TextContent, ToolResult
from typing import Any
from services.keybinds_service import KeybindService
from services.models.keybinds_model import EdAction


class PerformGameAction(ToolProtocol):
    readable_name = "Perform Game Action"  # Its for UI display
    # Its for UI display, Will be used to fetch a specific action from the
    # parameters dictionary, to later display it on UI.
    param_name = "action"
    name = "perform_game_action"
    description = "Perform a game action based on the provided type of action"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [action.value for action in EdAction],
            }
        },
        "required": ["action"],
    }

    def __init__(
        self,
        keybind_service: KeybindService,
    ):
        self.keybind_service = keybind_service

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_action = arguments.get("action")

        if raw_action is None:
            return self._error("Missing 'action' argument. Specify an action.")

        try:
            action = EdAction(raw_action)
        except ValueError:
            return self._error(f"Invalid 'action' argument: {raw_action}.")

        await self.keybind_service.perform_action(action)

        return ToolResult(
            content=TextContent(text=f"Performed game action: {action.value}"),
            is_error=False,
        ).to_dict()

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return ToolResult(
            content=TextContent(text=message),
            is_error=True,
        ).to_dict()
