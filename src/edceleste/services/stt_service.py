from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

import numpy as np
import whisper

from edceleste.services.exceptions.stt_exception import SttException
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.settings_service import SettingsService

import logging

if TYPE_CHECKING:
    import sounddevice as sd

logger = logging.getLogger(__name__)

_WHISPER_SAMPLE_RATE = 16_000

GAME_VOCABULARY_PROMPT = (
    "Celeste, is this system safe? What is in my hold? Do I have enough fuel for the "
    "next jump? Deploy hardpoints. Landing gear, cargo scoop, jettison cargo. Frame "
    "shift drive, FSD, supercruise. Flight assist off, boost. Four pips to systems, "
    "engines, weapons. Heat sink, chaff launcher, shield cell bank. Night vision, "
    "galaxy map, FSS."
)


class SttService:
    enabled: bool = True
    model: str | None = None
    input_device: int | None = None
    whisper_model: whisper.Whisper | None = None
    _recording_stream: sd.InputStream | None = None
    _recorded_frames: list[np.ndarray]

    def __init__(self, settings_service: SettingsService) -> None:
        """Only stores the settings service. The settings are applied in
        reload_service() and Whisper is loaded in cold_start() or on the first
        transcription."""
        self.__settings_service = settings_service
        self._recorded_frames = []

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Only checks that a Whisper model name is set, even when STT is
        disabled. Does not check that the name exists or that the input device
        works."""
        if not new_settings.stt.model:
            return SettingsIssueModel(
                section="stt",
                field="model",
                message="Model is not set.",
            )
        return None

    def start_recording(self) -> None:
        """Opens the microphone and returns at once. sounddevice records in
        its own thread and hands every chunk to _audio_recording_callback().
        Mono, 16 kHz, the format Whisper wants.

        Raises SttException when STT is disabled or a recording already runs.
        Frames left from an earlier recording are dropped.
        """
        import sounddevice as sd

        if not self.enabled:
            logger.info("STT is disabled. Cannot start recording.")
            raise SttException("STT is disabled. Cannot start recording.")
        if self._recording_stream is not None:
            logger.warning("Recording is already in progress.")
            raise SttException("Recording is already in progress.")
        self._recorded_frames = []
        self._recording_stream = sd.InputStream(
            samplerate=_WHISPER_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.input_device,
            callback=self._audio_recording_callback,
        )
        self._recording_stream.start()
        logger.info("Audio recording started.")

    def _audio_recording_callback(
        self, indata: np.ndarray, frames: int, time, status
    ) -> None:
        """Called by sounddevice from its audio thread for every chunk. Keeps a
        copy of the first channel, because sounddevice reuses the buffer.
        Problems such as lost input are only logged, recording goes on."""
        if status:
            logger.warning("Audio recording status: %s", status)
        self._recorded_frames.append(indata[:, 0].copy())

    def stop_recording_and_transcribe(self) -> str | None:
        """Stops the microphone AND turns the recording into text. Blocking
        and slow: it may load Whisper first and then transcribes on this
        thread.

        1. Raises SttException when no recording runs.
        2. Stops and closes the microphone stream.
        3. No audio captured -> returns None, Whisper is not called.
        4. Loads Whisper if needed (raises SttException when no model is set).
        5. Transcribes with GAME_VOCABULARY_PROMPT, so Whisper spells game
           words like "FSD" and "hardpoints" right.
        Returns None also when Whisper heard no words.
        """
        if self._recording_stream is None:
            logger.warning(
                "stop_recording_and_transcribe called but no recording is in progress."
            )
            raise SttException("No recording is in progress.")
        self._recording_stream.stop()
        self._recording_stream.close()
        self._recording_stream = None
        logger.info("Audio recording stopped.")

        if not self._recorded_frames:
            logger.warning("No audio data was captured during the recording.")
            return None

        whisper_model = self.load_stt_model()

        audio = np.concatenate(self._recorded_frames)
        self._recorded_frames = []
        result = whisper_model.transcribe(
            audio, fp16=False, initial_prompt=GAME_VOCABULARY_PROMPT
        )
        text: str = result.get("text", "")
        return text.strip() or None

    def reload_service(self):
        """Applies the saved STT settings. Called by cold_start() and after
        the settings change. A new model name or a changed enabled flag drops
        the loaded Whisper model, it is loaded again on the next use. A new
        input device is used from the next recording on. Does not load
        anything itself."""
        new_settings = self.__settings_service.get_settings()
        new_model = new_settings.stt.model
        new_enabled = new_settings.stt.enabled
        new_input_device = new_settings.stt.input_device
        if new_model != self.model or new_enabled != self.enabled:
            self.whisper_model = None
        self.enabled = new_enabled
        self.model = new_model
        self.input_device = new_input_device

    def is_stt_enabled(self) -> bool:
        """Reads the value applied by the last reload_service(), not the
        settings file. True before the first reload."""
        return self.enabled

    def get_stt_models(self) -> list[str]:
        """Every model name Whisper knows, downloaded or not. No network."""
        return whisper.available_models()

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        """Microphones as (name, sounddevice index), for the settings
        dropdown. Output only devices are left out. The same microphone can
        show up many times (once per Windows audio API), only the first index
        of each name is kept."""
        import sounddevice as sd

        all_devices = sd.query_devices()
        seen: dict[str, int] = {}
        for index, device in enumerate(all_devices):
            if device["max_input_channels"] > 0 and device["name"] not in seen:
                seen[device["name"]] = index
        return list(seen.items())

    def load_stt_model(self) -> whisper.Whisper:
        """Loads Whisper on the first call and keeps it, later calls return
        the same one. The first load is slow and blocking, and whisper
        downloads the model files from the internet when they are not cached
        yet. Raises SttException when no model name is set."""
        if not self.model:
            logger.warning("STT model is not set. Cannot load model.")
            raise SttException("STT model is not set. Cannot load model.")

        if self.whisper_model is None:
            logger.info("Loading Whisper model '%s' (lazy)...", self.model)
            self.whisper_model = whisper.load_model(self.model)

        return self.whisper_model

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Applies the settings and, when STT is enabled, loads Whisper now,
           so the first push to talk is fast. The load blocks the event loop.
        3. Yields completed. Never raises, an error ends up in the status
           message.
        """
        status = ColdStartStatus(
            service="stt",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status
        try:
            self.reload_service()
            if self.enabled:
                self.load_stt_model()
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
