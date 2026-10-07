from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.instinct_status import InstinctStatus
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class InstinctProtocol(BaseServiceProtocol, Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...

    def get_status(self) -> InstinctStatus: ...

    def get_download_size(self) -> int | None: ...

    def download_and_load_model_in_background(self) -> None: ...

    def cancel_download(self) -> None: ...
