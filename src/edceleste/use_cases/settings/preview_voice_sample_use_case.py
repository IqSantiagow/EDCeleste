from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol
from edceleste.services.models.settings_model import TtsProviderParams


class PreviewVoiceSampleUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(
        self, profile_name: str, text: str, params: TtsProviderParams
    ) -> None:
        """Slow. Generates new speech for the text with the profile (loads the
        voice model on first use), plays it at the saved volume and returns
        when the sound ends. params are the TTS settings as they are on the
        screen now. Nothing is saved."""
        await self.voice_cloning_protocol.preview_voice_sample(
            profile_name, text, params
        )
