from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsModel


class SettingsProtocol(BaseServiceProtocol):
    def get_settings(self) -> SettingsModel: ...

    def update_settings(self, new_settings: SettingsModel) -> None: ...
