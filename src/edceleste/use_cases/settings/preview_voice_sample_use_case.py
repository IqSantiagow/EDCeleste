from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class PreviewVoiceSampleUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(self, profile_name: str, text: str) -> None:
        await self.voice_cloning_protocol.preview_voice_sample(profile_name, text)
