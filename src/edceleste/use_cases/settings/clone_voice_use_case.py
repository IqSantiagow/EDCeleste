from typing import AsyncGenerator

from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.models.settings_model import TtsProviderParams
from edceleste.services.models.voice_cloning_models import VoiceCloningState


class CloneVoiceUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(
        self, path_to_audio_file: str, profile_name: str, params: TtsProviderParams
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Slow. Makes a voice profile from the first seconds of the audio file
        and passes every step on to the clone dialog. params are the TTS
        settings as they are on the screen now, saved or not. Writes the
        profile and its sample to the voices folder. An old profile with the
        same name is never overwritten. Does not change the settings. The
        errors (wrong provider, missing or too short file, name taken) come
        while iterating."""
        async for cloning_state in self.voice_cloning_protocol.clone_voice(
            path_to_audio_file, profile_name, params
        ):
            yield cloning_state
