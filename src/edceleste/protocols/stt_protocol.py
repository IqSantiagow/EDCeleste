from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class SttProtocol(BaseServiceProtocol, Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the stt part of settings that are not saved yet. Changes
        nothing in the service. None means fine."""
        ...

    def reload_service(self) -> None:
        """Reads the stt part of the saved settings. Does not load the Whisper
        model. When the model name or the enabled flag changed, it forgets the
        loaded model, so the next transcription loads it again."""
        ...

    def is_stt_enabled(self) -> bool:
        """The value from the last reload_service(), it does not read the
        settings again."""
        ...

    def get_stt_models(self) -> list[str]:
        """Names of the Whisper models the settings screen can offer. Fixed
        list from the whisper package, no network, nothing is downloaded."""
        ...

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        """Asks the sound system for devices that can record: (name, device
        index). Every name comes once, the first index wins."""
        ...

    def start_recording(self) -> None:
        """Opens the microphone and returns at once, the sound is collected in
        the background until stop_recording_and_transcribe(). Raises
        SttException when STT is disabled or a recording is already
        running."""
        ...

    def stop_recording_and_transcribe(self) -> str | None:
        """Stops the microphone and turns the recording into text. Blocking
        and slow: the first call loads the Whisper model, then it
        transcribes, so the UI runs it in a thread. None when nothing was
        recorded or nothing was heard. Raises SttException when no recording
        is running."""
        ...
