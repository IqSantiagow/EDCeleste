from typing import Protocol

from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class TTSProviderProtocol(Protocol):
    async def synthesize_and_play(self, text: str) -> None:
        """Turns the text into speech AND plays it on the speakers, with the
        Voice Lab effects and the configured volume. Returns only when the
        audio has finished playing."""
        ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks only the fields of this provider type. None means fine."""
        ...

    def reload_provider(self, new_settings: SettingsModel) -> None:
        """Takes new settings of the same provider type. Called by TTSService
        instead of building a new provider, so a loaded model can be kept."""
        ...
