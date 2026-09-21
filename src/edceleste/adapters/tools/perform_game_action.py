from pydantic_ai import ToolReturn

from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.settings_service import SettingsService


class PerformGameAction(ToolProtocol):
    readable_name = "Perform Game Action"  # Its for UI display
    # Its for UI display, Will be used to fetch a specific action from the
    # tool call arguments, to later display it on UI.
    param_name = "action"
    name = "perform_game_action"

    def __init__(
        self,
        keybind_service: KeybindService,
        settings_service: SettingsService,
    ):
        self.keybind_service = keybind_service
        self.settings_service = settings_service

    async def execute(self, action: EdAction) -> ToolReturn:
        """Perform a game action based on the provided type of action"""
        if not self.settings_service.get_settings().game_actions.enabled:
            return ToolReturn(
                return_value="Game actions are disabled by the user.",
                metadata={"is_error": True},
            )

        await self.keybind_service.perform_action(action)

        return ToolReturn(
            return_value=f"Performed game action: {action.value}",
            metadata={"is_error": False},
        )
