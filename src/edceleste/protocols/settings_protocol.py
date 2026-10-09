from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsModel


class SettingsProtocol(BaseServiceProtocol, Protocol):
    def get_settings(self) -> SettingsModel:
        """The settings kept in memory, does not read config.yaml again.
        Raises RuntimeError when config.yaml was never loaded or failed to
        load."""
        ...

    def save_settings(self, new_settings: SettingsModel) -> None:
        """Writes the settings to config.yaml (overwrites the file, creates it
        from config-example.yaml when missing) and keeps them in memory. Does
        not validate them and does not reload any service, the caller does
        that."""
        ...
