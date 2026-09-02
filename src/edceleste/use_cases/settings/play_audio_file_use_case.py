from edceleste.protocols.voice_cloning_protocol import VoiceCloningProtocol


class PlayAudioFileUseCase:
    def __init__(self, voice_cloning_protocol: VoiceCloningProtocol):
        self.voice_cloning_protocol = voice_cloning_protocol

    async def __call__(self, path_to_audio_file: str) -> None:
        await self.voice_cloning_protocol.play_audio_file(path_to_audio_file)
