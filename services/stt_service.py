import os
import whisper

from services.exceptions.stt_exception import SttException
from services.models.settings_model import SettingsIssueModel, SettingsModel
from services.settings_service import SettingsService

import logging

logger = logging.getLogger(__name__)


class SttService:
    enabled: bool = True
    model: str | None = None
    whisper_model: whisper.Whisper | None = None

    def __init__(self, settings_handler: SettingsService) -> None:
        self.__settings_handler = settings_handler
        self.reload_service()

    def handle_stt_request(self, audio_path: str) -> str | None:
        if not self.enabled:
            logger.info("STT is disabled. Cannot process audio.")
            raise SttException("STT is disabled. Cannot process audio.")

        if not self.model:
            logger.warning("STT model is not set. Cannot process audio.")
            raise SttException("STT model is not set. Cannot process audio.")

        if not audio_path or not os.path.exists(audio_path):
            logger.warning("Audio path is invalid or does not exist: %s", audio_path)
            raise SttException(
                f"Audio path is invalid or does not exist: {audio_path!r}"
            )

        if self.whisper_model is None:
            logger.info("Loading Whisper model '%s' (lazy)...", self.model)
            self.whisper_model = whisper.load_model(self.model)

        result = self.whisper_model.transcribe(audio_path)
        text: str = result.get("text", "")
        return text or None

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

    def reload_service(self):
        new_settings = self.__settings_handler.get_settings()
        new_model = new_settings.stt.model
        new_enabled = new_settings.stt.enabled
        if new_model != self.model or new_enabled != self.enabled:
            self.whisper_model = None
        self.enabled = new_enabled
        self.model = new_model

    def is_stt_enabled(self) -> bool:
        return self.enabled

    def get_stt_models(self) -> list[str]:
        return whisper.available_models()
