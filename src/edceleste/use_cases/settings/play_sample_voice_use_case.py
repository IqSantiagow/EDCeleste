from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class PlaySampleVoiceUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(self, profile_name: str) -> None:
        await self.voice_cloning_protocol.play_sample_voice(profile_name)
