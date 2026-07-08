from protocols.keybinds_protocol import KeybindsProtocol


class SettingsLoadKeybindsUseCase:
    """Parses the .binds file fresh, populating the keybinds cache"""

    def __init__(self, keybinds_protocol: KeybindsProtocol):
        self.keybinds_protocol = keybinds_protocol

    async def __call__(self):
        await self.keybinds_protocol.load_keybinds()
