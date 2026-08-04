from typing import Protocol

from services.models.settings_model import SettingsIssueModel, SettingsModel


class JournalWatcherProtocol(Protocol):
    def get_journal_healthcheck(self) -> bool: ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...
