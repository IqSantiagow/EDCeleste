from typing import Protocol

from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class EventReactionsProtocol(Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...
