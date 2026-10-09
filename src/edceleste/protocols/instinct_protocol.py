from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.instinct_status import InstinctStatus
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class InstinctProtocol(BaseServiceProtocol, Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Changes nothing in the service. Instinct has nothing to check yet,
        so it always returns None."""
        ...

    def reload_service(self) -> None:
        """Reads llm.instinct from the saved settings. A new device unloads the
        model, so it is loaded again on that device. Enabled: starts the
        download and load in the background. Disabled: unloads the model and
        gives the GPU memory back. Returns at once. Must run on the app event
        loop, because it may start an asyncio task."""
        ...

    def get_status(self) -> InstinctStatus:
        """Cheap snapshot for the settings screen, which polls it: model state,
        download progress, the device it runs on and the last failure. Only
        reads memory and checks one file on disk, no network."""
        ...

    def fetch_download_size(self) -> int | None:
        """Size of the model in bytes. Blocking: the first call asks the
        Hugging Face Hub over the network, later calls use the remembered
        value. None when the Hub cannot be reached, the next call tries
        again. Never raises."""
        ...

    def download_and_load_model_in_background(self) -> None:
        """Starts an asyncio task and returns at once. Does nothing when a
        download or load is already running. Skips the download when the model
        is already on disk. Loads the model only when Instinct is enabled in
        the settings. Errors are not raised, they end up in
        get_status().failure. Must run on the app event loop."""
        ...

    def cancel_download(self) -> None:
        """Only asks the running download to stop, it stops at the next chunk
        and deletes the half downloaded files. This is not a failure, so
        get_status() shows no error. Does nothing when no download is
        running."""
        ...
