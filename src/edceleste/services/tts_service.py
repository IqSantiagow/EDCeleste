import asyncio
import logging

import edge_tts

from edceleste.services.event_bus import EventBus
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.settings_service import SettingsService
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.tts_provider_protocol import TTSProviderProtocol

logger = logging.getLogger(__name__)

TTS_PROVIDER_CLASSES = {
    "edge": EdgeTTSProvider,
    "chatterbox": ChatterboxTTSProvider,
}


class TTSEvent:
    def __init__(self, text: str):
        self.text = text


class TTSService:
    def __init__(self, event_bus: EventBus, settings_handler: SettingsService) -> None:
        self.__event_bus = event_bus
        self.__settings_handler = settings_handler
        self.__event_bus.subscribe(TTSEvent, self.handle_tts_request)

        current_settings = self.__settings_handler.get_settings()
        self.provider_type = current_settings.tts.provider.type
        self.provider: TTSProviderProtocol = self.build_provider(current_settings)

    def build_provider(self, settings: SettingsModel) -> TTSProviderProtocol:
        provider_class = TTS_PROVIDER_CLASSES[settings.tts.provider.type]
        return provider_class(settings)

    async def synthesize(self, text):
        logger.info("Synthesizing TTS for text: %s", text)
        await self.provider.synthesize(text)

    async def handle_tts_request(self, event: TTSEvent):
        logger.info("Received TTS request: %s", event.text)
        await self.synthesize(event.text)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        return self.build_provider(new_settings).validate_settings(new_settings)

    def reload_service(self):
        new_settings = self.__settings_handler.get_settings()

        if new_settings.tts.provider.type != self.provider_type:
            self.provider_type = new_settings.tts.provider.type
            self.provider = self.build_provider(new_settings)
        else:
            self.provider.reload_provider(new_settings)

    async def get_tts_voices(self) -> list[str]:
        return [voice["ShortName"] for voice in await edge_tts.list_voices()]

    async def clone_voice(self, path_to_audio_file: str, profile_name: str) -> None:
        if not isinstance(self.provider, ChatterboxTTSProvider):
            raise VoiceCloningException(
                "The active TTS provider does not support voice cloning. "
                "Switch the TTS provider to 'chatterbox' and try again."
            )

        logger.info(
            "Cloning voice profile '%s' from audio file: %s",
            profile_name,
            path_to_audio_file,
        )
        await asyncio.to_thread(
            self.provider.clone_voice, path_to_audio_file, profile_name
        )
