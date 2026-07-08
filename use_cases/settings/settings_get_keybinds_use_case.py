from protocols.keybinds_protocol import KeybindsProtocol
from services.models.keybinds_model import Keybind


class SettingsGetKeybindsUseCase:
    def __init__(self, keybinds_protocol: KeybindsProtocol):
        self.keybinds_protocol = keybinds_protocol

    def __call__(self) -> list[Keybind]:
        return self.keybinds_protocol.get_keybinds()
