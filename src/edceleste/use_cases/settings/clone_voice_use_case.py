from typing import AsyncGenerator

from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.tts_providers.chatterbox_tts_provider import VoiceCloningState


class CloneVoiceUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(
        self, path_to_audio_file: str, profile_name: str
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Slow. Makes a chatterbox voice profile from the first 10 s of the
        audio file and passes every step on to the clone dialog. Writes the
        profile and its sample to the voices folder, an old profile with the
        same name is overwritten. Does not change the settings. The errors
        (wrong provider, missing or too short file) come while iterating."""
        async for cloning_state in self.voice_cloning_protocol.clone_voice(
            path_to_audio_file, profile_name
        ):
            yield cloning_state
