from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.models.settings_model import TtsProviderParams


class PlaySampleVoiceUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(self, profile_name: str, params: TtsProviderParams) -> None:
        """Plays the sample saved when the profile was cloned, nothing is
        generated, so it is fast. params are the TTS settings as they are on the
        screen now: they say which provider's folder the sample is in. Returns
        when the sound ends. Raises VoiceCloningException when that provider
        cannot clone voices and FileNotFoundError when the sample is missing."""
        await self.voice_cloning_protocol.play_sample_voice(profile_name, params)
