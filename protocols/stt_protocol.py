from typing import Protocol

from services.models.settings_model import SettingsIssueModel, SettingsModel


class SttProtocol(Protocol):
    def handle_stt_request(self, audio_path: str) -> str | None: ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...

    def is_stt_enabled(self) -> bool: ...

    def get_stt_models(self) -> list[str]: ...
