from typing import Protocol

from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class TTSProviderProtocol(Protocol):
    async def synthesize(self, text: str) -> None: ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_provider(self, new_settings: SettingsModel) -> None: ...
