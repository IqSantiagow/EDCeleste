from edceleste.protocols.keybinds_protocol import KeybindsProtocol
from edceleste.services.models.keybinds_model import Keybind


class SettingsGetKeybindsUseCase:
    def __init__(self, keybinds_protocol: KeybindsProtocol):
        self.keybinds_protocol = keybinds_protocol

    def __call__(self) -> list[Keybind]:
        """Only reads the keybinds cache, not the .binds file. Run
        SettingsLoadKeybindsUseCase first to see changes made in the game.
        Actions without a keyboard key are in the list with key=None."""
        return self.keybinds_protocol.get_keybinds()
