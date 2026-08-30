import asyncio
import logging
import os

import edge_tts
import sounddevice as sd
import soundfile as sf

from edceleste.services.models.settings_model import (
    EdgeTTSProviderModel,
    SettingsIssueModel,
    SettingsModel,
)
from edceleste.services.tts_providers.tts_provider_protocol import TTSProviderProtocol

logger = logging.getLogger(__name__)

SYNTHESIZED_SPEECH_FILE = "output.mp3"


class EdgeTTSProvider(TTSProviderProtocol):
    def __init__(self, config: SettingsModel):
        self.config = config

    @property
    def provider_settings(self) -> EdgeTTSProviderModel:
        return self.config.tts.provider  # type: ignore[return-value]

    async def synthesize(self, text: str) -> None:
        logger.info(
            "Synthesizing speech with the Edge provider using voice %s.",
            self.provider_settings.voice,
        )

        audio_output = edge_tts.Communicate(text, voice=self.provider_settings.voice)
        await audio_output.save(SYNTHESIZED_SPEECH_FILE)

        speech_samples, sample_rate = sf.read(SYNTHESIZED_SPEECH_FILE)

        sd.play(speech_samples * self.config.tts.volume, sample_rate)

        await asyncio.sleep(len(speech_samples) / sample_rate)

        os.remove(SYNTHESIZED_SPEECH_FILE)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if not new_settings.tts.provider.voice:  # type: ignore[union-attr]
            return SettingsIssueModel(
                section="tts",
                field="voice",
                message="Voice is not set.",
            )
        return None

    def reload_provider(self, new_settings: SettingsModel) -> None:
        self.config = new_settings
