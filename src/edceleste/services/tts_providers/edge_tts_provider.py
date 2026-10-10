import logging
import os
from pathlib import Path

import edge_tts
import numpy as np
import soundfile as sf

from edceleste.services.models.settings_model import (
    EdgeParamsModel,
    SettingsIssueModel,
    TtsProviderParams,
)
from edceleste.services.tts_providers.tts_provider_protocol import TTSProviderProtocol

logger = logging.getLogger(__name__)

SYNTHESIZED_SPEECH_FILE = "output.mp3"


class EdgeTTSProvider(TTSProviderProtocol):
    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        """Speaks the text with the Edge voice from params. Goes to the network.

        1. Sends the text to the Microsoft Edge voice service and saves the
           mp3 as output.mp3 in the current working folder.
        2. Reads it back into memory and deletes the file.
        Returns the samples and the sample rate, plays nothing. Raises
        TypeError for params of another provider. Network errors are raised,
        then output.mp3 may stay on disk. profile_path is not used.
        """
        if not isinstance(params, EdgeParamsModel):
            raise TypeError(f"Edge TTS needs EdgeParamsModel, got {type(params)}")

        logger.info(
            "Synthesizing speech with the Edge provider using voice %s.", params.voice
        )

        audio_output = edge_tts.Communicate(text, voice=params.voice)
        await audio_output.save(SYNTHESIZED_SPEECH_FILE)

        speech_samples, sample_rate = sf.read(SYNTHESIZED_SPEECH_FILE)
        os.remove(SYNTHESIZED_SPEECH_FILE)

        return speech_samples, sample_rate

    def validate_params(self, params: TtsProviderParams) -> SettingsIssueModel | None:
        """Only checks that a voice is set. Does not ask the network if the
        voice exists. Raises TypeError for params of another provider."""
        if not isinstance(params, EdgeParamsModel):
            raise TypeError(f"Edge TTS needs EdgeParamsModel, got {type(params)}")

        if not params.voice:
            return SettingsIssueModel(
                section="tts",
                field="voice",
                message="Voice is not set.",
            )
        return None
