from protocols.settings_protocol import SettingsProtocol
from services.models.settings_model import SettingsModel


class GetSettingsUseCase:
    def __init__(self, settings_protocol: SettingsProtocol):
        self.settings_protocol = settings_protocol

    def __call__(self) -> SettingsModel:
        return self.settings_protocol.get_settings()
