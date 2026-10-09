from pydantic_ai import ToolReturn

from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.exceptions.game_window_exception import (
    GameWindowNotFoundException,
)
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
        """Only stores the dependencies. The game_actions switch is read on
        every execute(), so turning it off works without a reload."""
        self.keybind_service = keybind_service
        self.settings_service = settings_service

    # pydantic_ai sends the docstring below to the LLM as the tool description,
    # so it is written for the LLM, not for us. How it works: presses the key
    # bound to the action in the game. Three failures come back as a ToolReturn
    # with is_error=True in the metadata, so the LLM can tell the pilot: game
    # actions switched off in the settings, action without a keyboard key, or
    # game window not found (then nothing is pressed). Any other error from
    # KeybindService is raised as it is.
    async def execute(self, action: EdAction) -> ToolReturn:
        """Perform a game action based on the provided type of action"""
        if not self.settings_service.get_settings().game_actions.enabled:
            return ToolReturn(
                return_value="Game actions are disabled by the user.",
                metadata={"is_error": True},
            )

        if not self.keybind_service.is_bound(action):
            return ToolReturn(
                return_value=f"{action.value} is not bound to a keyboard key.",
                metadata={"is_error": True},
            )

        try:
            await self.keybind_service.press_keys_for_action(action)
        except GameWindowNotFoundException:
            return ToolReturn(
                return_value="Game window not found, nothing was pressed.",
                metadata={"is_error": True},
            )

        return ToolReturn(
            return_value=f"Performed game action: {action.value}",
            metadata={"is_error": False},
        )
