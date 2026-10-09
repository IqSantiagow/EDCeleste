from edceleste.protocols.keybinds_protocol import KeybindsProtocol


class SettingsLoadKeybindsUseCase:
    """Parses the .binds file fresh, populating the keybinds cache"""

    def __init__(self, keybinds_protocol: KeybindsProtocol):
        self.keybinds_protocol = keybinds_protocol

    def __call__(self):
        """Reads the newest .binds file from the saved keybindings path, not
        from the path being edited. Raises FileNotFoundError or
        MissingKeybindsError, and then the old cache stays."""
        self.keybinds_protocol.load_keybinds()
