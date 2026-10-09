from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class PreviewVoiceSampleUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(self, profile_name: str, text: str) -> None:
        """Slow. Generates new speech for the text with the profile (loads the
        voice model on first use), adds the voice lab effects, plays it and
        returns when the sound ends. Nothing is saved."""
        await self.voice_cloning_protocol.preview_voice_sample(profile_name, text)
