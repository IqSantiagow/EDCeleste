from typing import Protocol

from pydantic_ai import ToolReturn

from edceleste.services.models.keybinds_model import EdAction


class PerformGameActionProtocol(Protocol):
    async def perform_game_action(self, action: EdAction) -> ToolReturn:
        """Presses the key bound to the action in the game.

        Expected failures (feature off, no key, game window not found) are
        returned, not raised: a ToolReturn with metadata={"is_error": True}. An
        action the ship cannot do right now comes back with
        metadata={"unavailable": True} and the reason as the text, nothing is
        pressed.
        """
        ...
