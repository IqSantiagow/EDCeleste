from protocols.keybinds_protocol import KeybindsProtocol


class SettingsLoadKeybindsUseCase:
    """Used only to get loaded keybinds, not for refetching them"""

    def __init__(self, keybinds_protocol: KeybindsProtocol):
        self.keybinds_protocol = keybinds_protocol

    async def __call__(self):
        await self.keybinds_protocol.load_keybinds()
