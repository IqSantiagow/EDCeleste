from typing import Protocol

from services.models.settings_model import SettingsIssueModel, SettingsModel


class TTSProtocol(Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> list[SettingsIssueModel]: ...

    def reload_service(self) -> None: ...
