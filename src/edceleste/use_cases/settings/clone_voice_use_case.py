from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class CloneVoiceUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(self, path_to_audio_file: str, profile_name: str) -> None:
        await self.voice_cloning_protocol.clone_voice(path_to_audio_file, profile_name)
