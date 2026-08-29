import asyncio
import logging
import os

import edge_tts
import sounddevice as sd
import soundfile as sf

from edceleste.services.event_bus import EventBus
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


class TTSEvent:
    def __init__(self, text: str):
        self.text = text


class TTSService:
    def __init__(
        self, voice, event_bus: EventBus, settings_handler: SettingsService
    ) -> None:
        self.voice = voice
        self.__event_bus = event_bus
        self.__settings_handler = settings_handler
        self.__event_bus.subscribe(TTSEvent, self.handle_tts_request)

        self.reload_service()

    async def synthesize(self, text):
        audio_output = edge_tts.Communicate(text, voice=self.voice)
        logger.info("Synthesizing TTS for text: %s", text)

        await audio_output.save("output.mp3")

        data, samplerate = sf.read("output.mp3")

        sd.play(data, samplerate)

        await asyncio.sleep(len(data) / samplerate)

        os.remove("output.mp3")

    async def handle_tts_request(self, event: TTSEvent):
        logger.info("Received TTS request: %s", event.text)
        await self.synthesize(event.text)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if not new_settings.tts.voice:
            return SettingsIssueModel(
                section="tts",
                field="voice",
                message="Voice is not set.",
            )
        return None

    def reload_service(self):
        new_settings = self.__settings_handler.get_settings()
        self.voice = new_settings.tts.voice

    async def get_tts_voices(self) -> list[str]:
        return [voice["ShortName"] for voice in await edge_tts.list_voices()]
