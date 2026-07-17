from protocols.settings_protocol import SettingsProtocol
from services.models.settings_model import SettingsModel


class GetSettingsUseCase:
    def __init__(self, settings_repository: SettingsProtocol):
        self.settings_repository = settings_repository

    def __call__(self) -> SettingsModel:
        return self.settings_repository.get_settings()
