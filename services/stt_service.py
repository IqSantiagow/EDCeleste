import os
import whisper

from services.models.settings_model import SettingsIssueModel, SettingsModel
from services.event_bus import EventBus
from services.settings_service import SettingsService

import logging

logger = logging.getLogger(__name__)


class SttEvent:
    def __init__(self, text: str):
        self.text = text


class SttService:
    model: str | None = None

    def __init__(self, event_bus: EventBus, settings_handler: SettingsService) -> None:
        self.__event_bus = event_bus
        self.__settings_handler = settings_handler
        self.reload_service()

    def handle_stt_request(self, audio_path: str) -> str | None:
        # TODO: Add error handling for when the model is not set, and logic on frontend
        if not self.model:
            logger.warning("STT model is not set. Cannot process audio.")
            return None

        if not audio_path or not os.path.exists(audio_path):
            logger.warning("Audio path is invalid or does not exist: %s", audio_path)
            return None

        whisper_model = whisper.load_model(self.model)

        result = whisper_model.transcribe(audio_path)

        text: str = result.get("text", "")  # type: ignore
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
        self.model = new_settings.stt.model
