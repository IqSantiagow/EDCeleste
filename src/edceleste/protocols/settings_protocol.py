from typing import Protocol
from edceleste.services.models.settings_model import SettingsModel


class SettingsProtocol(Protocol):
    def get_settings(self) -> SettingsModel: ...

    def update_settings(self, new_settings: SettingsModel) -> None: ...
