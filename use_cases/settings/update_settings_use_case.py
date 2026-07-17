from protocols.settings_protocol import SettingsProtocol
from services.models.settings_model import SettingsModel


class UpdateSettingsUseCase:
    def __init__(self, settings_repository: SettingsProtocol):
        self.settings_repository = settings_repository

    def __call__(self, new_settings: SettingsModel):
        self.settings_repository.update_settings(new_settings)
