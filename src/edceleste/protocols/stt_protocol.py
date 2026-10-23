from collections.abc import AsyncGenerator
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
        loaded model, so the next transcription loads it again. It also moves
        the push-to-talk key (stt.hotkey): the key of the last reload is
        unregistered, the new one is registered, and from then on its press
        calls start_recording() and its release stops the recording and
        transcribes it in the background, the text comes out of
        consume_stt_queue()."""
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
        index). Every name comes once, the first index wins. An empty list
        means no microphone. An error of the sound system (PortAudio) is not
        caught."""
        ...

    def start_recording(self) -> None:
        """Opens the microphone and returns at once, the sound is collected in
        the background until stop_recording_and_transcribe(). Raises
        SttException when STT is disabled or a recording is already
        running. Otherwise Celeste goes silent first (the speech that is
        playing is cut off, the waiting speech is dropped)."""
        ...

    def stop_recording_and_transcribe(self) -> None:
        """Stops the microphone and turns the recording into text. Blocking
        and slow: the first call loads the Whisper model, then it
        transcribes, so the UI and the hotkey run it in a thread. Returns
        nothing, the text comes out of consume_stt_queue(), and nothing comes
        out when nothing was recorded or heard. Raises SttException when no
        recording is running."""
        ...

    def consume_stt_queue(self) -> AsyncGenerator[str, None]:
        """Never ends. Yields every text that stop_recording_and_transcribe()
        puts in the queue, one by one. The stream has exactly one consumer, a
        queue does not duplicate items."""
        ...
