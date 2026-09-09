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


class SttService:
    enabled: bool = True
    model: str | None = None
    input_device: int | None = None
    whisper_model: whisper.Whisper | None = None
    _recording_stream: sd.InputStream | None = None
    _recorded_frames: list[np.ndarray]

    def __init__(self, settings_handler: SettingsService) -> None:
        self.__settings_handler = settings_handler
        self._recorded_frames = []

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if not new_settings.stt.model:
            return SettingsIssueModel(
                section="stt",
                field="model",
                message="Model is not set.",
            )
        return None

    def start_recording(self) -> None:
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
        if status:
            logger.warning("Audio recording status: %s", status)
        self._recorded_frames.append(indata[:, 0].copy())

    def stop_recording(self) -> str | None:
        if self._recording_stream is None:
            logger.warning("stop_recording called but no recording is in progress.")
            raise SttException("No recording is in progress.")
        self._recording_stream.stop()
        self._recording_stream.close()
        self._recording_stream = None
        logger.info("Audio recording stopped.")

        if not self._recorded_frames:
            logger.warning("No audio data was captured during the recording.")
            return None

        self.load_stt_model()

        audio = np.concatenate(self._recorded_frames)
        self._recorded_frames = []
        result = self.whisper_model.transcribe(audio, fp16=False)
        text: str = result.get("text", "")
        return text.strip() or None

    def reload_service(self):
        new_settings = self.__settings_handler.get_settings()
        new_model = new_settings.stt.model
        new_enabled = new_settings.stt.enabled
        new_input_device = new_settings.stt.input_device
        if new_model != self.model or new_enabled != self.enabled:
            self.whisper_model = None
        self.enabled = new_enabled
        self.model = new_model
        self.input_device = new_input_device

    def is_stt_enabled(self) -> bool:
        return self.enabled

    def get_stt_models(self) -> list[str]:
        return whisper.available_models()

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        import sounddevice as sd

        all_devices = sd.query_devices()
        seen: dict[str, int] = {}
        for index, device in enumerate(all_devices):
            if device["max_input_channels"] > 0 and device["name"] not in seen:
                seen[device["name"]] = index
        return list(seen.items())

    def load_stt_model(self) -> None:
        if not self.model:
            logger.warning("STT model is not set. Cannot load model.")
            raise SttException("STT model is not set. Cannot load model.")

        if self.whisper_model is None:
            logger.info("Loading Whisper model '%s' (lazy)...", self.model)
            self.whisper_model = whisper.load_model(self.model)

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
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
