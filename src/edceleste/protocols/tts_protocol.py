from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class TTSProtocol(BaseServiceProtocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...

    async def get_tts_voices(self) -> list[str]: ...
