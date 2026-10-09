from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class EventReactionsProtocol(BaseServiceProtocol, Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the event_reactions part of settings that are not saved yet.
        Changes nothing in the service. None means fine."""
        ...

    def reload_service(self) -> None:
        """Reads the saved settings again, so the next journal event is checked
        against the new list of events Celeste replies to by herself."""
        ...
