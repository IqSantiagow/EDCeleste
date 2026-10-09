from edceleste.protocols.settings_protocol import SettingsProtocol
from edceleste.services.models.settings_model import SettingsModel


class GetSettingsUseCase:
    def __init__(self, settings_protocol: SettingsProtocol):
        self.settings_protocol = settings_protocol

    def __call__(self) -> SettingsModel:
        """The saved settings kept in memory, config.yaml is not read again.
        Raises RuntimeError when the settings were never loaded."""
        return self.settings_protocol.get_settings()
