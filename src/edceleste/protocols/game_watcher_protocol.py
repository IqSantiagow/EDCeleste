from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class GameWatcherProtocol(BaseServiceProtocol, Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Looks on disk: the journal path from settings that are not saved yet
        must exist and hold .log files. Changes nothing in the service. None
        means fine."""
        ...

    def reload_service(self) -> None:
        """Stops the running file watchers and starts new ones on the journal
        path from the saved settings. Starts asyncio tasks, so it must run on
        the app event loop. Returns at once, the watchers keep running in the
        background. Raises FileNotFoundError when the folder has no journal
        file."""
        ...
